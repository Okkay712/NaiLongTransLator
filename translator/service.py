"""翻译任务调度。

设计：
- 通过 subprocess.Popen 调用 manga_translator
- 通过 asyncio.Queue 实现批量任务串行执行（同一时刻只跑一个）
- 任务日志 + 进度走 asyncio.Queue，SSE 端点消费任务队列
- 输出位置由配置 output_mode / output_dir 决定：
    "input"  → <输入父目录>/<输入名>_CN  （与原行为一致）
    "custom" → <输出目录>/<输入名>_CN    （output_dir 为空时回退到 ~/Trans_Output）
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import config as cfg_mod
from .paths import project_root
from .settings import default_output_dir

PROGRESS_RE = re.compile(r"Translating\s+(\d+)/(\d+)", re.IGNORECASE)
# 引擎保存译图时的输出行：
#   [local] Saving "C:\..."          (旧版)
#   [manga-translator.local] Saving "C:\..."  (新版)
SAVING_RE = re.compile(r'\[(?:manga-translator\.)?local\]\s+Saving\s+"(?P<path>[^"]+)"')


# 任务状态机：
#   idle / queued / starting / running / done / failed / cancelled / cancelling
TASK_STATES_RUNNABLE = {"queued", "starting", "running"}


@dataclass
class Task:
    id: str
    folder: str
    status: str = "idle"
    current: int = 0
    total: int = 0
    log: list = field(default_factory=list)
    output_path: Optional[str] = None
    process: Optional[subprocess.Popen] = None
    queue: Optional[asyncio.Queue] = None
    started_at: float = 0.0
    # 批量上下文：该任务在批量提交里的索引（0-based），以及批量总数
    batch_index: int = 0
    batch_total: int = 1


TASKS: dict[str, Task] = {}
WORK_QUEUE: "asyncio.Queue[Task]" = asyncio.Queue()
_WORKER_STARTED = False
_WORKER_LOCK = asyncio.Lock() if False else None  # 占位，asyncio.Lock 在 event loop 创建后才能用


# ---------- 路径解析 ----------

def _venv_python() -> Path:
    root = project_root()
    if os.name == "nt":
        cand = root / ".venv" / "Scripts" / "python.exe"
    else:
        cand = root / ".venv" / "bin" / "python"
    return cand if cand.exists() else Path(sys.executable)


def resolve_output_path(folder: str, cfg: dict) -> Path:
    """根据配置的 output_mode / output_dir 解析输出目录。

    - output_mode == "input" 或 output_dir 为空且用户没显式 custom：
      行为与旧版本一致：<folder 父目录>/<folder 名>_CN
    - output_mode == "custom" + output_dir 有值：
      →  <output_dir>/<folder 名>_CN（自动展开 ~，目录存在性在调用方负责）
    - output_mode == "custom" + output_dir 为空：
      →  默认 ~/Trans_Output/<folder 名>_CN
    """
    p = Path(folder)
    mode = (cfg.get("output_mode") or "input").lower()
    if mode == "custom":
        out_root = (cfg.get("output_dir") or "").strip()
        if not out_root:
            out_root = str(default_output_dir())
        return Path(out_root).expanduser() / (p.name + "_CN")
    # 默认/旧版行为
    return p.parent / (p.name + "_CN")


# 注意：原 _resolve_output 名字保留以兼容旧测试
def _resolve_output(folder: str) -> Path:
    return resolve_output_path(folder, cfg_mod.load())


# ---------- 命令构造 ----------

def build_command(folder: str, cfg: dict) -> tuple[list[str], dict, Path]:
    """构造 manga_translator subprocess 的命令、环境和 engine config 路径。"""
    root = project_root()
    py = _venv_python()

    env = os.environ.copy()
    env["HF_HOME"] = str(root / "models" / "huggingface")
    env["TRANSFORMERS_CACHE"] = str(root / "models" / "huggingface" / "transformers")
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"  # 让子进程不缓冲 stdout，PyWebView 抓得到每行
    # 引擎源码在 engine/manga-image-translator-main 下；通过 PYTHONPATH 让
    # `python -m manga_translator` 能找到模块（manga-image-translator 不在 PyPI）。
    src_dir = root / "engine" / "manga-image-translator-main"
    if src_dir.exists():
        env["PYTHONPATH"] = str(src_dir) + os.pathsep + env.get("PYTHONPATH", "")

    # 翻译器 API key 注入：当前只支持 deepseek
    if cfg.get("api_key") and cfg.get("translator") == "deepseek":
        env["DEEPSEEK_API_KEY"] = cfg["api_key"]
        env["DEEPSEEK_API_BASE"] = "https://api.deepseek.com"
        env["DEEPSEEK_MODEL"] = "deepseek-chat"

    # 引擎配置写到工程根的 engine_config.json（被 manga_translator 读取）
    engine_cfg = {
        "translator": {
            "translator": cfg.get("translator") or "deepseek",
            "target_lang": cfg.get("target_lang") or "CHS",
        },
        "detector": {"detector": cfg.get("detector") or "default"},
        "ocr": {"ocr": cfg.get("ocr") or "48px"},
        "inpainter": {"inpainter": cfg.get("inpainter") or "default"},
        "render": {"direction": "auto", "alignment": "auto"},
    }
    engine_cfg_path = root / "engine_config.json"
    engine_cfg_path.write_text(
        json.dumps(engine_cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    output_dir = resolve_output_path(folder, cfg)

    cmd = [
        str(py), "-u",  # -u = unbuffered，stdout 不走块缓冲
        "-m", "manga_translator", "local",
        "-v", "--overwrite",
        "--model-dir", str(root / "models"),
        "--font-path", cfg.get("font") or r"C:\Windows\Fonts\simhei.ttf",
        "--config-file", str(engine_cfg_path),
        "--save-quality", str(cfg.get("save_quality") or 95),
        "-i", str(Path(folder).resolve()),
        "-o", str(output_dir.resolve()),
    ]
    return cmd, env, engine_cfg_path


# ---------- 任务生命周期 ----------

async def run_task(task: Task) -> None:
    assert task.queue is not None
    q = task.queue

    task.status = "starting"
    await q.put({"type": "status", "status": "starting"})

    cfg = cfg_mod.load()
    cmd, env, _ = build_command(task.folder, cfg)
    await q.put({"type": "log", "text": "[奶龙翻译器] 命令：" + " ".join(cmd)})

    # 自定义输出目录时确保存在
    try:
        Path(cmd[-2]).parent.mkdir(parents=True, exist_ok=True)  # type: ignore[index]
    except Exception as e:  # noqa: BLE001
        await q.put({"type": "log", "text": f"[奶龙翻译器] 创建输出目录失败：{e}"})

    # Windows 上避免 CREATE_NEW_CONSOLE 弹黑窗；CREATE_NO_WINDOW 不开新 console
    # stdout=PIPE / stderr=STDOUT 容易让 tqdm 的 `\r` 行被 pipe 缓冲，PYTHONUNBUFFERED + -u 已经处理
    popen_kwargs = dict(
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
        cwd=str(project_root()),
        text=True,
        bufsize=1,
        errors="replace",  # 任何编码怪字符不会让 readline 抛 UnicodeDecodeError
    )
    if os.name == "nt":
        popen_kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    proc = subprocess.Popen(cmd, **popen_kwargs)
    task.process = proc
    task.status = "running"
    task.started_at = asyncio.get_event_loop().time()
    await q.put({"type": "status", "status": "running"})

    loop = asyncio.get_event_loop()
    line_count = 0
    while True:
        line = await loop.run_in_executor(None, proc.stdout.readline)
        if not line:
            break
        line = line.rstrip()
        task.log.append(line)
        line_count += 1
        # 剥掉 ANSI 转义码（\x1b[...m），前端 textContent 会显示成乱码字符
        clean = re.sub(r"\x1b\[[0-9;]*m", "", line)
        await q.put({"type": "log", "text": clean})
        m = PROGRESS_RE.search(line)
        if m:
            task.current = int(m.group(1))
            task.total = int(m.group(2))
            await q.put({"type": "progress", "current": task.current, "total": task.total})

        sm = SAVING_RE.search(line)
        if sm:
            saved_path = sm.group("path")
            # 尝试在输入文件夹找同 stem 的原图（路径可能有不同扩展名）
            orig_path = None
            try:
                sp = Path(saved_path)
                if task.folder:
                    for cand in Path(task.folder).rglob(sp.stem + ".*"):
                        if cand.is_file() and cand.suffix.lower() in {
                            ".jpg", ".jpeg", ".png", ".webp", ".bmp"
                        }:
                            orig_path = str(cand.resolve())
                            break
            except Exception:
                pass
            await q.put({
                "type": "image_saved",
                "path": saved_path,
                "orig_path": orig_path,
            })

        if task.status == "cancelling":
            try:
                proc.terminate()
            except Exception:
                pass
            break

    rc = proc.wait()
    await q.put({
        "type": "log",
        "text": f"[奶龙翻译器] 子进程退出，共 {line_count} 行日志，rc={rc}",
    })
    if task.status == "cancelling":
        task.status = "cancelled"
        await q.put({"type": "done", "ok": False, "cancelled": True, "rc": rc})
        return
    if rc == 0:
        out = resolve_output_path(task.folder, cfg)
        task.output_path = str(out.resolve())
        task.status = "done"
        await q.put({"type": "done", "ok": True, "output_path": task.output_path, "rc": rc})
    else:
        task.status = "failed"
        await q.put({"type": "done", "ok": False, "rc": rc})


async def queue_worker() -> None:
    """后台 worker：从 WORK_QUEUE 里一个一个取出来跑，保证串行。"""
    while True:
        task = await WORK_QUEUE.get()
        try:
            await run_task(task)
        except Exception as e:  # noqa: BLE001
            try:
                task.status = "failed"
                if task.queue is not None:
                    await task.queue.put({
                        "type": "done", "ok": False, "error": str(e),
                    })
            except Exception:
                pass


def ensure_worker() -> None:
    """在主事件循环里启动一次 worker。"""
    global _WORKER_STARTED
    if _WORKER_STARTED:
        return
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        # 没在事件循环里（如同步上下文），延后到下一次异步入口
        return
    asyncio.create_task(queue_worker())
    _WORKER_STARTED = True


async def enqueue(folder: str, batch_index: int = 0, batch_total: int = 1) -> Task:
    """入队一个翻译任务，由 worker 串行执行。"""
    ensure_worker()
    tid = uuid.uuid4().hex[:12]
    q: asyncio.Queue = asyncio.Queue()
    task = Task(
        id=tid, folder=folder, queue=q, status="queued",
        batch_index=batch_index, batch_total=batch_total,
    )
    TASKS[tid] = task
    await WORK_QUEUE.put(task)
    return task


def cancel(task_id: str) -> bool:
    """取消任务。如果还在队列里就直接标记 cancelled，否则终止子进程。"""
    t = TASKS.get(task_id)
    if not t:
        return False
    if t.status in {"done", "failed", "cancelled"}:
        return False
    t.status = "cancelling"
    if t.process is not None:
        try:
            t.process.terminate()
        except Exception:
            return False
    return True


def queue_snapshot() -> list[dict]:
    """返回当前任务列表快照，供前端查看批量进度。"""
    items = []
    for t in TASKS.values():
        items.append({
            "task_id": t.id,
            "folder": t.folder,
            "status": t.status,
            "batch_index": t.batch_index,
            "batch_total": t.batch_total,
            "current": t.current,
            "total": t.total,
            "output_path": t.output_path,
        })
    # 按 batch_index 排，未批量任务的 batch_index=0 也合理
    items.sort(key=lambda x: (x["batch_index"], x["task_id"]))
    return items


# 兼容旧 start() 别名（保留给可能的单元测试）
async def start(folder: str) -> Task:
    return await enqueue(folder)
