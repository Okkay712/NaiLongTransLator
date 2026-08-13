import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"
MODELS = ROOT / "models"
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def load_config():
    with CONFIG.open("r", encoding="utf-8") as f:
        return json.load(f)


def natural_key(path: Path):
    import re
    return [int(x) if x.isdigit() else x.lower() for x in re.split(r"(\d+)", path.name)]


def normalize_input(src: Path) -> Path:
    if src.is_file() and src.suffix.lower() == ".zip":
        target = ROOT / "work" / (src.stem + "_unzipped")
        if target.exists():
            shutil.rmtree(target)
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(src, "r") as zf:
            zf.extractall(target)
        return target
    if not src.exists() or not src.is_dir():
        raise SystemExit(f"找不到图片文件夹：{src}")
    return src


def collect_images(folder: Path):
    return sorted([p for p in folder.rglob("*") if p.suffix.lower() in IMAGE_EXTS], key=natural_key)


def make_ordered_stage(src_folder: Path, images):
    stage = ROOT / "work" / f"stage_{int(time.time())}"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True, exist_ok=True)
    for idx, img in enumerate(images, 1):
        ext = ".jpg" if img.suffix.lower() in {".jpeg", ".jpg"} else img.suffix.lower()
        shutil.copy2(img, stage / f"{idx:03d}{ext}")
    return stage


def zip_folder(folder: Path):
    zip_path = folder.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(folder.rglob("*"), key=natural_key):
            if p.is_file():
                zf.write(p, p.relative_to(folder))
    return zip_path


def run_engine(stage: Path, output: Path, cfg):
    output.mkdir(parents=True, exist_ok=True)
    MODELS.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["HF_HOME"] = str(MODELS / "huggingface")
    env["TRANSFORMERS_CACHE"] = str(MODELS / "huggingface" / "transformers")
    env["PYTHONIOENCODING"] = "utf-8"
    engine_src = ROOT / "engine" / "manga-image-translator-main"
    if engine_src.exists():
        env["PYTHONPATH"] = str(engine_src) + os.pathsep + env.get("PYTHONPATH", "")

    cmd = [
        sys.executable,
        "-m",
        "manga_translator",
        "local",
        "-v",
        "--overwrite",
        "--model-dir",
        str(MODELS),
        "--font-path",
        cfg.get("font", r"C:\Windows\Fonts\simhei.ttf"),
        "-i",
        str(stage),
        "-o",
        str(output),
        "--save-quality",
        str(cfg.get("save_quality", 100)),
    ]

    # The upstream engine reads most choices from config. Keep a small config beside output.
    engine_config = ROOT / "engine_config.json"
    engine_config.write_text(
        json.dumps(
            {
                "translator": {
                    "translator": cfg.get("translator", "youdao"),
                    "target_lang": cfg.get("target_lang", "CHS"),
                },
                "detector": {"detector": cfg.get("detector", "default")},
                "ocr": {"ocr": cfg.get("ocr", "48px")},
                "inpainter": {"inpainter": cfg.get("inpainter", "default")},
                "render": {"direction": "auto", "alignment": "auto"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    cmd += ["--config-file", str(engine_config)]

    print("开始翻译：", stage)
    print("输出目录：", output)
    print("命令：", " ".join(f'"{x}"' if " " in x else x for x in cmd))
    subprocess.check_call(cmd, cwd=ROOT, env=env)


def gui():
    import tkinter as tk
    from tkinter import filedialog, messagebox

    root = tk.Tk()
    root.title("Trans 漫画图片自动翻译器")
    root.geometry("560x220")

    selected = tk.StringVar()

    def choose():
        path = filedialog.askdirectory(title="选择图片文件夹")
        if path:
            selected.set(path)

    def start():
        path = selected.get().strip()
        if not path:
            messagebox.showwarning("请选择文件夹", "先选择一个包含图片的文件夹。")
            return
        try:
            out, zp = translate(Path(path))
            messagebox.showinfo("完成", f"输出目录：\n{out}\n\n压缩包：\n{zp}")
        except Exception as e:
            messagebox.showerror("翻译失败", str(e))

    tk.Label(root, text="选择包含 JPG/PNG/WEBP 的漫画图片文件夹").pack(pady=(22, 8))
    tk.Entry(root, textvariable=selected, width=70).pack(pady=4)
    tk.Button(root, text="选择文件夹", command=choose, width=18).pack(pady=6)
    tk.Button(root, text="开始翻译", command=start, width=18).pack(pady=8)
    root.mainloop()


def translate(input_path: Path):
    cfg = load_config()
    src = normalize_input(input_path.resolve())
    images = collect_images(src)
    if not images:
        raise SystemExit("这个文件夹里没有找到 jpg/png/webp 图片。")
    stage = make_ordered_stage(src, images)
    output = src.parent / f"{src.name}_CN"
    if output.exists():
        shutil.rmtree(output)
    run_engine(stage, output, cfg)
    zip_path = zip_folder(output) if cfg.get("zip_result", True) else None
    return output, zip_path


def main():
    parser = argparse.ArgumentParser(description="批量漫画图片翻译器")
    parser.add_argument("input", nargs="?", help="图片文件夹或 zip 文件")
    args = parser.parse_args()
    if not args.input:
        gui()
        return
    out, zp = translate(Path(args.input))
    print("完成：", out)
    if zp:
        print("压缩包：", zp)


if __name__ == "__main__":
    main()
