"""FastAPI 应用。

路由分两段：
1. /api/*  业务接口（settings / status / translate / stream / install ...）
2. /      静态前端页面（index / task / install）
"""
from __future__ import annotations

import asyncio
import json
import platform
import subprocess
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse

from . import config as cfg_mod
from . import installer
from . import service
from .paths import frozen_data_dir, project_root

app = FastAPI(title="奶龙翻译器", version="0.2.0")

ROOT = project_root()


def _frontend_dir() -> "Path | None":
    """返回静态前端目录。开发模式在项目根；frozen 模式在 _internal/。"""
    dev = ROOT / "frontend"
    if dev.exists():
        return dev
    fd = frozen_data_dir()
    if fd and (fd / "frontend").exists():
        return fd / "frontend"
    return None


FRONTEND = _frontend_dir()


# Windows 上不要闪黑窗口；非 Windows 平台没有 CREATE_NO_WINDOW 常量，置 None
def _no_window_kwargs() -> dict:
    if platform.system() == "Windows":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


# ---------- 状态 / 设置 / 历史 ----------

@app.get("/api/status")
def status():
    s = installer.is_engine_installed()
    cfg = cfg_mod.load()
    return {
        "has_config": bool(cfg.get("api_key")),
        "target_lang": cfg.get("target_lang"),
        "engine_installed": s,
        "version": app.version,
        "busy": any(
            t.status in {"starting", "running"}
            for t in service.TASKS.values()
        ),
    }


@app.get("/api/settings")
def get_settings():
    return cfg_mod.masked(cfg_mod.load())


@app.post("/api/settings")
def save_settings(payload: dict):
    if not isinstance(payload, dict):
        raise HTTPException(400, "payload 必须是 dict")
    current = cfg_mod.load()
    for k, v in payload.items():
        if k not in current:
            continue
        if k == "api_key" and v == "***":
            continue
        current[k] = v
    cfg_mod.save(current)
    return cfg_mod.masked(current)


@app.get("/api/history")
def history():
    return {"recent": cfg_mod.get_history()}


# ---------- 文件夹选择 ----------

def _ps_pick_folder(description: str) -> str:
    """调 Windows 原生 FolderBrowserDialog，返回所选路径或空。"""
    if platform.system() != "Windows":
        return ""
    ps = (
        "Add-Type -AssemblyName System.Windows.Forms | Out-Null; "
        "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
        f"$f.Description = '{description}'; "
        "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.SelectedPath }"
    )
    r = subprocess.run(
        ["powershell", "-NoProfile", "-Command", ps],
        capture_output=True, text=True, timeout=180,
        **_no_window_kwargs(),
    )
    return (r.stdout or "").strip()


@app.post("/api/pick-folder")
def pick_folder():
    try:
        path = _ps_pick_folder("选择图片文件夹")
        if path:
            cfg_mod.add_history(path)
        return {"path": path}
    except subprocess.TimeoutExpired:
        raise HTTPException(408, "选择超时")
    except Exception as e:
        raise HTTPException(500, f"选择失败：{e}")


@app.post("/api/pick-output-dir")
def pick_output_dir():
    """选择输出目录（不同于输入）。空字符串时使用默认 ~/Trans_Output。"""
    from .settings import default_output_dir
    try:
        # 把默认目录作为打开起点
        default = str(default_output_dir())
        Path(default).mkdir(parents=True, exist_ok=True)
        if platform.system() == "Windows":
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms | Out-Null; "
                "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
                f"$f.Description = '选择输出目录（默认 {default}）'; "
                "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.SelectedPath }"
            )
            r = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps],
                capture_output=True, text=True, timeout=180,
                **_no_window_kwargs(),
            )
            path = (r.stdout or "").strip()
        else:
            path = ""
        return {"path": path, "default": default}
    except subprocess.TimeoutExpired:
        raise HTTPException(408, "选择超时")
    except Exception as e:
        raise HTTPException(500, f"选择失败：{e}")


# ---------- 翻译任务 ----------

async def _enqueue_folder(folder: str, batch_index: int = 0, batch_total: int = 1):
    folder = folder.strip()
    if not folder:
        return None
    if not Path(folder).exists() or not Path(folder).is_dir():
        raise HTTPException(400, f"文件夹不存在：{folder}")
    cfg_mod.add_history(folder)
    return await service.enqueue(folder, batch_index=batch_index, batch_total=batch_total)


@app.post("/api/translate")
async def translate(payload: dict):
    """接受单文件夹 (folder) 或文件夹列表 (folders)。"""
    if not isinstance(payload, dict):
        payload = {}
    folders_raw = payload.get("folders")
    if folders_raw is None:
        # 兼容旧的单 folder 调用
        single = (payload.get("folder") or "").strip()
        folders = [single] if single else []
    else:
        if not isinstance(folders_raw, list):
            raise HTTPException(400, "folders 必须是数组")
        folders = [str(f).strip() for f in folders_raw if str(f).strip()]

    if not folders:
        raise HTTPException(400, "缺少 folder / folders 参数")
    if not installer.is_engine_installed():
        raise HTTPException(412, "翻译引擎未安装，请先在主页触发安装")

    task_ids: list[str] = []
    batch_total = len(folders)
    for idx, folder in enumerate(folders):
        t = await _enqueue_folder(folder, batch_index=idx, batch_total=batch_total)
        if t is not None:
            task_ids.append(t.id)

    if not task_ids:
        raise HTTPException(400, "没有任何有效文件夹")
    return {
        "task_ids": task_ids,
        "first_task_id": task_ids[0],
        "batch_total": batch_total,
    }


@app.post("/api/cancel/{task_id}")
def cancel_task(task_id: str):
    ok = service.cancel(task_id)
    if not ok:
        raise HTTPException(404, "任务不存在或无法取消")
    return {"ok": True}


@app.get("/api/queue")
def queue():
    return {"tasks": service.queue_snapshot()}


@app.get("/api/input-images")
def input_images(folder: str):
    """列出输入文件夹下的图片文件（按文件名排序），给前端"原图"预览用。"""
    p = Path(folder)
    if not p.exists() or not p.is_dir():
        raise HTTPException(404, f"文件夹不存在：{folder}")
    exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
    files = sorted(
        str(f.resolve()) for f in p.rglob("*")
        if f.is_file() and f.suffix.lower() in exts
    )
    return {"files": files}


@app.get("/api/preview")
def preview(path: str):
    """安全地提供图片文件：仅放行常见图片后缀，且文件必须存在且是文件。"""
    p = Path(path).resolve()
    if not p.exists() or not p.is_file():
        raise HTTPException(404, "文件不存在")
    if p.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}:
        raise HTTPException(400, "不是图片文件")
    return FileResponse(str(p))


@app.get("/api/output-default")
def output_default():
    from .settings import default_output_dir
    return {"path": str(default_output_dir())}


@app.post("/api/open")
def open_path(payload: dict):
    """reveal 一个路径（用资源管理器打开或选中）。"""
    if not isinstance(payload, dict):
        raise HTTPException(400, "payload 必须是 dict")
    target = (payload.get("path") or "").strip()
    if not target:
        raise HTTPException(400, "缺少 path")
    p = Path(target)
    if not p.exists():
        raise HTTPException(404, f"路径不存在：{target}")
    try:
        if platform.system() == "Windows":
            # /select 选中文件；如果传的是目录则直接打开
            if p.is_file():
                subprocess.run(["explorer", "/select,", str(p)],
                               check=False, timeout=10)
            else:
                subprocess.run(["explorer", str(p)],
                               check=False, timeout=10)
        else:
            subprocess.run(["xdg-open", str(p.parent)], check=False, timeout=10)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(500, f"打开失败：{e}")


@app.get("/api/stream/{task_id}")
async def stream(task_id: str):
    task = service.TASKS.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    queue = task.queue

    async def gen():
        yield {"event": "hello",
               "data": json.dumps({
                   "task_id": task_id,
                   "folder": task.folder,
                   "batch_index": task.batch_index,
                   "batch_total": task.batch_total,
               })}
        while True:
            msg = await queue.get()
            yield {"event": msg.get("type", "msg"),
                   "data": json.dumps(msg, ensure_ascii=False)}
            if msg.get("type") == "done":
                break

    return EventSourceResponse(gen())


# ---------- 引擎首次安装 ----------

INSTALL_STATE: dict = {"running": False, "queue": None, "started_at": 0}


@app.get("/api/install/stream")
async def install_stream():
    if INSTALL_STATE["queue"] is None:
        INSTALL_STATE["queue"] = asyncio.Queue()

    if not INSTALL_STATE["running"]:
        asyncio.create_task(_run_install(INSTALL_STATE["queue"]))

    async def gen():
        q = INSTALL_STATE["queue"]
        while True:
            msg = await q.get()
            yield {"event": msg.get("type", "msg"),
                   "data": json.dumps(msg, ensure_ascii=False)}
            if msg.get("type") == "done":
                break

    return EventSourceResponse(gen())


async def _run_install(q: asyncio.Queue):
    if INSTALL_STATE["running"]:
        return
    INSTALL_STATE["running"] = True
    try:
        if installer.is_engine_installed():
            await q.put({"type": "log", "text": "[奶龙翻译器] 引擎已安装，跳过。"})
            await q.put({"type": "done", "ok": True, "already": True})
            return
        await installer.run_install(q)
    except Exception as e:
        await q.put({"type": "done", "ok": False, "error": str(e)})
    finally:
        INSTALL_STATE["running"] = False


# ---------- 静态前端 ----------

if FRONTEND.exists():
    @app.get("/")
    def index():
        return FileResponse(FRONTEND / "index.html")

    @app.get("/task.html")
    def task_page():
        return FileResponse(FRONTEND / "task.html")

    @app.get("/install.html")
    def install_page():
        return FileResponse(FRONTEND / "install.html")

    @app.get("/settings.html")
    def settings_page():
        return FileResponse(FRONTEND / "settings.html")

    @app.get("/batch.html")
    def batch_page():
        return FileResponse(FRONTEND / "batch.html")

    app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
