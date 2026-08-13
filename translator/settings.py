"""服务端运行时配置（端口、默认值等）。"""
from __future__ import annotations

import socket

HOST = "127.0.0.1"


def _free_port(preferred: int = 8765, span: int = 30) -> int:
    """寻找一个可用端口，从 preferred 开始尝试。"""
    for p in range(preferred, preferred + span):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((HOST, p))
                return p
            except OSError:
                continue
    raise RuntimeError("找不到可用端口")


PORT = _free_port()


CONFIG_DEFAULTS: dict = {
    "api_key": "",
    "target_lang": "CHS",
    "translator": "deepseek",
    "font": r"C:\Windows\Fonts\simhei.ttf",
    "save_quality": 95,
    "detector": "default",
    "ocr": "48px",
    "inpainter": "default",
    "output_mode": "custom",   # "input" = 同输入目录；"custom" = 自定义 output_dir
    "output_dir": "",          # 空 = 用默认的 ~/Trans_Output
    "advanced_visible": False,
}


def default_output_dir() -> "Path":
    """解析默认输出目录：~/Trans_Output。"""
    from pathlib import Path
    return Path.home() / "Trans_Output"
