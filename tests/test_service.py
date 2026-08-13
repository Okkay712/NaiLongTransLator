"""translator.service 的状态机测试。

不真正调用 manga_translator（依赖太大、装不上时 CI 也跑不了）。
用 hello.py 这种一次性脚本作为假引擎，验证 running / done / cancelling 三种路径。
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def fake_engine(tmp_path: Path):
    """写一个假引擎脚本：每次打印一行 'Translating X/N'，然后空转直到 stdin/stdout 关闭。"""
    engine = tmp_path / "fake_engine.py"
    engine.write_text(
        "import sys, time, signal\n"
        "running = True\n"
        "def stop(*_):\n"
        "    global running\n"
        "    running = False\n"
        "signal.signal(signal.SIGTERM, stop)\n"
        "for i in range(1, 6):\n"
        "    print(f'translating Translating {i}/5', flush=True)\n"
        "    print(f'extra log line {i}', flush=True)\n"
        "    time.sleep(0.05)\n"
        "sys.exit(0)\n",
        encoding="utf-8",
    )
    return engine


@pytest.mark.asyncio
async def test_state_machine_done(monkeypatch, tmp_path, fake_engine):
    """成功路径：5 行进度 + done 事件"""
    from translator import service

    # 把 build_command 替成直接跑假引擎
    def fake_build(folder, cfg):
        return [sys.executable, str(fake_engine), folder], {}, tmp_path / "engine_config.json"

    monkeypatch.setattr(service, "build_command", fake_build)
    monkeypatch.setattr(service, "_resolve_output", lambda f: tmp_path / "out")

    # 必要占位：config 加载不爆就行
    q: asyncio.Queue = asyncio.Queue()
    task = service.Task(id="t1", folder=str(tmp_path), queue=q)
    service.TASKS["t1"] = task

    await service.run_task(task)

    events = []
    while not q.empty():
        events.append(q.get_nowait())

    types = [e["type"] for e in events]
    assert "status" in types
    assert "progress" in types
    assert types[-1] == "done"
    done = events[-1]
    assert done["ok"] is True
    assert task.status == "done"


@pytest.mark.asyncio
async def test_state_machine_cancel(monkeypatch, tmp_path, fake_engine):
    """取消路径：设置 task.status='cancelling' 后子进程被终止。"""
    from translator import service

    # 慢一点：每个 Translating 间隔 0.2s
    slow = tmp_path / "slow.py"
    slow.write_text(
        "import sys, time\n"
        "for i in range(1, 4):\n"
        "    print(f'Translating {i}/3', flush=True)\n"
        "    time.sleep(0.3)\n",
        encoding="utf-8",
    )

    def fake_build(folder, cfg):
        return [sys.executable, str(slow), folder], {}, tmp_path / "engine_config.json"

    monkeypatch.setattr(service, "build_command", fake_build)
    monkeypatch.setattr(service, "_resolve_output", lambda f: tmp_path / "out")

    q: asyncio.Queue = asyncio.Queue()
    task = service.Task(id="t2", folder=str(tmp_path), queue=q)
    service.TASKS["t2"] = task

    async def kick_cancel_after_first_progress():
        # 等到拿到第一条 progress 事件再取消
        for _ in range(50):
            await asyncio.sleep(0.05)
            try:
                msg = q.get_nowait()
                if msg.get("type") == "progress":
                    task.status = "cancelling"
                    return
            except asyncio.QueueEmpty:
                continue

    kicker = asyncio.create_task(kick_cancel_after_first_progress())
    await service.run_task(task)
    await kicker

    events = []
    while not q.empty():
        events.append(q.get_nowait())
    done = events[-1]
    assert done["type"] == "done"
    assert done["cancelled"] is True
    assert task.status == "cancelled"


def test_resolve_output(tmp_path):
    from translator import service
    folder = tmp_path / "input_dir"
    out = service.resolve_output_path(str(folder), {"output_mode": "input"})
    assert out.name == "input_dir_CN"
    assert out.parent == tmp_path


def test_venv_python_falls_back(tmp_path, monkeypatch):
    """project_root() 没 .venv 时回退到当前 python 解释器。"""
    from translator import service
    monkeypatch.setattr(service, "project_root", lambda: tmp_path)
    py = service._venv_python()
    # 应返回当前解释器
    assert py == Path(sys.executable)
