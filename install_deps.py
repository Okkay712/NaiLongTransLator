import os
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
PY = VENV / "Scripts" / "python.exe"
REQ = ROOT / "requirements.txt"
RUNTIME_REQ = ROOT / "requirements.runtime.txt"
ENGINE = ROOT / "engine"
ENGINE_URL = "https://github.com/zyddnys/manga-image-translator/archive/refs/heads/main.zip"


def run(cmd):
    print(">", " ".join(map(str, cmd)))
    subprocess.check_call([str(c) for c in cmd], cwd=ROOT)


def main():
    if not VENV.exists():
        run([sys.executable, "-m", "venv", VENV])
    ENGINE.mkdir(exist_ok=True)
    src_dir = ENGINE / "manga-image-translator-main"
    if not src_dir.exists():
        archive = ENGINE / "manga-image-translator-main.zip"
        print("正在下载漫画翻译引擎源码...")
        urllib.request.urlretrieve(ENGINE_URL, archive)
        print("正在解压引擎源码...")
        with zipfile.ZipFile(archive, "r") as zf:
            zf.extractall(ENGINE)
    env = os.environ.copy()
    env["HF_HOME"] = str(ROOT / "models" / "huggingface")
    env["TRANSFORMERS_CACHE"] = str(ROOT / "models" / "huggingface" / "transformers")
    subprocess.check_call([str(PY), "-m", "pip", "install", "--upgrade", "pip"], cwd=ROOT, env=env)

    # 新版前端依赖（FastAPI + PyWebView 等）
    if RUNTIME_REQ.exists():
        print()
        print("=" * 60)
        print("安装新版前端依赖 (FastAPI / PyWebView / ...)")
        print("=" * 60)
        subprocess.check_call([str(PY), "-m", "pip", "install", "--no-cache-dir", "-r", str(RUNTIME_REQ)], cwd=ROOT, env=env)

    # 保留兼容：原 engine 入口依赖
    subprocess.check_call([str(PY), "-m", "pip", "install", "--ignore-requires-python", "-r", str(REQ)], cwd=ROOT, env=env)
    source_req = src_dir / "requirements.txt"
    if source_req.exists():
        filtered_req = ROOT / "requirements.engine.filtered.txt"
        skipped = ("pydensecrf",)
        lines = []
        for line in source_req.read_text(encoding="utf-8").splitlines():
            clean = line.strip().lower()
            if clean and not clean.startswith("#") and any(name in clean for name in skipped):
                print(f"跳过可选依赖：{line}")
                continue
            lines.append(line)
        filtered_req.write_text("\n".join(lines) + "\n", encoding="utf-8")
        subprocess.check_call([str(PY), "-m", "pip", "install", "--ignore-requires-python", "-r", str(filtered_req)], cwd=src_dir, env=env)
    print()
    print("依赖安装完成。下一步双击 启动翻译器.bat")


if __name__ == "__main__":
    main()
