"""首次运行时的引擎安装。

来源：manga-image-translator **不在 PyPI 上**，只在 GitHub。
安装流程（沿用 install_deps.py 的逻辑）：
  1) 从 GitHub 拉源码 zip，解压到 engine/manga-image-translator-main/
  2) 装它的依赖（过滤掉 pydensecrf 这种可选的、装不上的）

通过 `run_install(queue)` 异步把每步进度写进 asyncio.Queue 给 SSE 推送。
"""
from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

from .paths import project_root

ENGINE_URL = (
    "https://github.com/zyddnys/manga-image-translator/archive/"
    "refs/heads/main.zip"
)
SKIPPED_DEPS = ("pydensecrf",)
# 引擎钉死 numpy==1.26.4 会和 opencv-python-headless 4.13.x（要 numpy>=2）打架。
# 拿掉这一行让 pip 用现场已有的 numpy（一般是 2.x），不主动降级也不主动装。
STRIPPED_PINS = ("numpy",)


def _venv_python() -> Path:
    """返回项目 .venv 里的 python.exe；不存在则回退到当前解释器。"""
    root = project_root()
    if os.name == "nt":
        cand = root / ".venv" / "Scripts" / "python.exe"
    else:
        cand = root / ".venv" / "bin" / "python"
    if cand.exists():
        return cand
    return Path(sys.executable)


def _popen_kwargs() -> dict:
    """Windows 上不开新 console，避免点安装/验证时闪黑窗口。"""
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def is_engine_installed() -> bool:
    """检测 manga_translator 是否可 import。

    manga_translator 不在 PyPI、没被 pip install，只能从源码目录 import，
    所以必须把 engine/src 加到 PYTHONPATH 里再开子进程验证。
    """
    src = engine_source_dir()
    if not (src / "manga_translator").exists():
        return False
    py = _venv_python()
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONPATH"] = str(src) + os.pathsep + env.get("PYTHONPATH", "")
    try:
        r = subprocess.run(
            [str(py), "-c",
             "import manga_translator; print('ok')"],
            capture_output=True, text=True, timeout=30,
            env=env,
            **_popen_kwargs(),
        )
        return "ok" in r.stdout
    except Exception:
        return False


def engine_source_dir() -> Path:
    return project_root() / "engine" / "manga-image-translator-main"


async def run_install(q: asyncio.Queue) -> None:
    """完整安装流程；每条产出推一条 {"type":"log",...} 到 q；最后推 {"type":"done",...}。"""
    root = project_root()
    py = _venv_python()
    engine_dir = root / "engine"
    src_dir = engine_dir / "manga-image-translator-main"

    try:
        # 1) 下载源码（如已存在则跳过）
        if src_dir.exists():
            await q.put({"type": "log", "text": "[奶龙翻译器] 跳过：引擎源码已存在。"})
        else:
            engine_dir.mkdir(parents=True, exist_ok=True)
            archive = engine_dir / "manga-image-translator-main.zip"
            await q.put({
                "type": "log",
                "text": f"[奶龙翻译器] 步骤 1/2：下载引擎源码 → {archive}",
            })
            await q.put({
                "type": "log",
                "text": f"[奶龙翻译器] URL: {ENGINE_URL}",
            })

            def _download():
                urllib.request.urlretrieve(ENGINE_URL, archive)
            await asyncio.get_event_loop().run_in_executor(None, _download)
            await q.put({"type": "log", "text": "[奶龙翻译器] 下载完成，开始解压…"})

            def _extract():
                with zipfile.ZipFile(archive, "r") as zf:
                    zf.extractall(engine_dir)
            await asyncio.get_event_loop().run_in_executor(None, _extract)
            await q.put({"type": "log", "text": f"[奶龙翻译器] 解压完成：{src_dir}"})

        if not (src_dir / "manga_translator").exists():
            await q.put({
                "type": "log",
                "text": "[奶龙翻译器] 警告：源码结构异常，缺少 manga_translator/，请检查网络或版本。",
            })
            await q.put({"type": "done", "ok": False, "error": "源码结构异常"})
            return

        # 2) 装引擎依赖
        env = os.environ.copy()
        env["HF_HOME"] = str(root / "models" / "huggingface")
        env["TRANSFORMERS_CACHE"] = str(root / "models" / "huggingface" / "transformers")
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONPATH"] = str(src_dir) + os.pathsep + env.get("PYTHONPATH", "")

        source_req = src_dir / "requirements.txt"
        if not source_req.exists():
            await q.put({"type": "done", "ok": False, "error": "找不到引擎的 requirements.txt"})
            return

        # 过滤掉我们已知装不上的（pydensecrf），避免子进程直接挂
        # 还要拿掉 numpy 这种强行降级的 pin，让 pip 用现场已有的版本
        filtered_req = root / "requirements.engine.filtered.txt"
        lines = []
        for line in source_req.read_text(encoding="utf-8").splitlines():
            clean = line.strip().lower()
            if not clean or clean.startswith("#"):
                lines.append(line)
                continue
            if any(name in clean for name in SKIPPED_DEPS):
                await q.put({"type": "log", "text": f"[奶龙翻译器] 跳过可选依赖：{line}"})
                continue
            if any(clean.startswith(f"{name}==") or clean.startswith(f"{name}>=")
                   for name in STRIPPED_PINS):
                await q.put({
                    "type": "log",
                    "text": f"[奶龙翻译器] 拿掉强制 pin：{line}（避免和 opencv-python-headless 等打架）",
                })
                continue
            lines.append(line)
        filtered_req.write_text("\n".join(lines) + "\n", encoding="utf-8")

        await q.put({
            "type": "log",
            "text": f"[奶龙翻译器] 步骤 2/2：安装引擎依赖（跳过 {','.join(SKIPPED_DEPS)}）",
        })
        cmd = [
            str(py), "-m", "pip", "install", "--no-cache-dir", "-r", str(filtered_req),
        ]
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            env=env,
            **_popen_kwargs(),
        )
        assert proc.stdout is not None
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            await q.put({
                "type": "log",
                "text": line.decode("utf-8", errors="replace").rstrip(),
            })
        rc = await proc.wait()
        if rc != 0:
            await q.put({"type": "done", "ok": False, "rc": rc})
            return

        # 3) 验证：实际跑一次 import 并把 stderr 打出来，便于排查
        verify_py = _venv_python()
        verify_env = os.environ.copy()
        verify_env["PYTHONIOENCODING"] = "utf-8"
        verify_env["PYTHONPATH"] = str(src_dir) + os.pathsep + verify_env.get("PYTHONPATH", "")
        try:
            vr = subprocess.run(
                [str(verify_py), "-c", "import manga_translator; print('ok')"],
                capture_output=True, text=True, timeout=30, env=verify_env,
                **_popen_kwargs(),
            )
        except Exception as e:  # noqa: BLE001
            await q.put({"type": "log", "text": f"[奶龙翻译器] 验证异常：{e}"})
            await q.put({"type": "done", "ok": False, "error": str(e)})
            return
        if "ok" in vr.stdout:
            await q.put({"type": "log", "text": "[奶龙翻译器] ✓ manga_translator 安装成功"})
            await q.put({"type": "done", "ok": True})
        else:
            err_tail = (vr.stderr or "").strip().splitlines()[-3:]
            await q.put({
                "type": "log",
                "text": "[奶龙翻译器] import manga_translator 失败，最后几行错误：\n"
                        + "\n".join(err_tail),
            })
            await q.put({"type": "done",
                         "ok": False,
                         "error": "import manga_translator 失败"})
    except Exception as e:  # noqa: BLE001
        await q.put({"type": "done", "ok": False, "error": str(e)})
