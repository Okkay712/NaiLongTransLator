"""新增功能：输出路径解析 + 批量任务队列。"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

from translator import service


# ---------- 输出路径解析 ----------

def test_resolve_output_input_mode(tmp_path: Path):
    """output_mode == 'input' 时使用旧行为。"""
    folder = tmp_path / "input_dir"
    cfg = {"output_mode": "input"}
    out = service.resolve_output_path(str(folder), cfg)
    assert out == folder.parent / (folder.name + "_CN")


def test_resolve_output_custom_uses_output_dir(tmp_path: Path):
    folder = tmp_path / "manga1"
    out_dir = tmp_path / "out"
    cfg = {"output_mode": "custom", "output_dir": str(out_dir)}
    out = service.resolve_output_path(str(folder), cfg)
    assert out == out_dir / (folder.name + "_CN")


def test_resolve_output_custom_empty_falls_back_to_default(tmp_path: Path):
    """output_dir 为空时回退到 ~/Trans_Output。"""
    folder = tmp_path / "manga_x"
    cfg = {"output_mode": "custom", "output_dir": ""}
    out = service.resolve_output_path(str(folder), cfg)
    # default 输出目录就是 ~/Trans_Output
    assert out.name == "manga_x_CN"
    assert out.parent.name == "Trans_Output"
    # 必须展开 ~ 路径（不会是字面 ~）
    assert "~" not in str(out)


def test_resolve_output_tilde_expansion(tmp_path: Path):
    """output_dir 里写 ~/foo 会被展开到用户主目录下的 foo。"""
    folder = tmp_path / "manga_y"
    cfg = {"output_mode": "custom", "output_dir": "~/Trans_Output_test"}
    out = service.resolve_output_path(str(folder), cfg)
    assert out.name == "manga_y_CN"
    assert "Trans_Output_test" in str(out)
    assert "~" not in str(out)


def test_resolve_output_default_mode_when_missing_key(tmp_path: Path):
    """output_mode 缺失时按 'input' 旧行为处理（向后兼容）。"""
    folder = tmp_path / "legacy"
    cfg = {}
    out = service.resolve_output_path(str(folder), cfg)
    assert out == folder.parent / (folder.name + "_CN")


# ---------- 批量任务队列 ----------

@pytest.mark.asyncio
async def test_enqueue_creates_queued_task(monkeypatch, tmp_path):
    """enqueue 应该立刻入队，状态为 queued。"""
    # 重置全局 TASKS（避免 fixture 串扰）
    service.TASKS.clear()
    monkeypatch.setattr(service, "ensure_worker", lambda: None)  # 阻止实际 worker 启动

    folder = tmp_path / "b1"
    folder.mkdir()
    task = await service.enqueue(str(folder))
    assert task.status == "queued"
    assert task.id in service.TASKS
    assert service.TASKS[task.id] is task
    # 没有 worker 实际跑，状态应一直 queued
    await asyncio.sleep(0.05)
    assert service.TASKS[task.id].status == "queued"


@pytest.mark.asyncio
async def test_queue_snapshot_orders_by_batch_index(monkeypatch, tmp_path):
    service.TASKS.clear()
    monkeypatch.setattr(service, "ensure_worker", lambda: None)

    a = tmp_path / "a"; a.mkdir()
    b = tmp_path / "b"; b.mkdir()
    c = tmp_path / "c"; c.mkdir()
    await service.enqueue(str(a), batch_index=0, batch_total=3)
    await service.enqueue(str(b), batch_index=1, batch_total=3)
    await service.enqueue(str(c), batch_index=2, batch_total=3)

    snap = service.queue_snapshot()
    assert len(snap) == 3
    # 排序后 batch_index 是升序
    assert [s["folder"] for s in snap] == [str(a), str(b), str(c)]
    assert all(s["batch_total"] == 3 for s in snap)


@pytest.mark.asyncio
async def test_worker_runs_sequentially(monkeypatch, tmp_path):
    """两个 fake 任务应该串行执行（看 done 的先后）。"""
    service.TASKS.clear()
    service.WORK_QUEUE = asyncio.Queue()

    # 用 fake_engine 复用之前的思路
    fake = tmp_path / "fake.py"
    fake.write_text(
        "import sys, time\n"
        "for i in range(2):\n"
        "    print('tick', flush=True)\n"
        "    time.sleep(0.05)\n",
        encoding="utf-8",
    )

    async def fake_run(task):
        # 不真跑 subprocess：直接把队列填上 done 事件
        await asyncio.sleep(0.05)
        task.status = "done"
        if task.queue is not None:
            await task.queue.put({"type": "done", "ok": True, "output_path": "x"})

    monkeypatch.setattr(service, "run_task", fake_run)

    # 启动临时 worker
    worker = asyncio.create_task(service.queue_worker())
    try:
        a = tmp_path / "a"; a.mkdir()
        b = tmp_path / "b"; b.mkdir()
        await service.enqueue(str(a), batch_index=0, batch_total=2)
        await service.enqueue(str(b), batch_index=1, batch_total=2)

        # 等所有任务状态变为 done 或超过 2 秒
        for _ in range(40):
            await asyncio.sleep(0.05)
            if all(t.status == "done" for t in service.TASKS.values()):
                break
        assert all(t.status == "done" for t in service.TASKS.values()), \
            f"未都完成：{[t.status for t in service.TASKS.values()]}"
    finally:
        # 取消 worker：放一个 poison pill 让它在下次 get 退出（最稳）
        worker.cancel()
        try:
            await worker
        except (asyncio.CancelledError, Exception):
            pass
