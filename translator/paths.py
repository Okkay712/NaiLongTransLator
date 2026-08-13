"""路径工具。所有跨模块用到的路径常量集中在这里。"""
from __future__ import annotations

import os
import sys
from pathlib import Path


def project_root() -> Path:
    """返回项目根目录。

    开发模式：translator 包的父目录。
    打包后（PyInstaller COLLECT 单目录布局）：
    - sys.executable 指向 Trans.exe
    - 数据文件（frontend/）放在 <exe 父目录>/_internal/frontend/
      注意 PyInstaller 在 _MEIPASS 设置的根就是 _internal/，exe 上一层才更稳。
    """
    if getattr(sys, "frozen", False):
        # COLLECT 模式下：MEIPASS = <dist>/Trans/_internal/
        # exe = <dist>/Trans/Trans.exe
        # 视为 "exe 所在目录就是项目根"
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def frozen_data_dir() -> Path | None:
    """返回打包后的数据目录。开发模式下返回 None。

    PyInstaller COLLECT 后，数据在 <exe 父目录>/_internal/frontend/。
    sys._MEIPASS 一并兼容单文件模式（虽然我们用单目录）。
    """
    if not getattr(sys, "frozen", False):
        return None
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass)
    return Path(sys.executable).resolve().parent / "_internal"


# 用户配置目录。允许通过环境变量覆盖（便于测试）。
_USER_DIR_OVERRIDE = os.environ.get("TRANS_USER_DIR")
USER_CONFIG_DIR: Path = (
    Path(_USER_DIR_OVERRIDE) if _USER_DIR_OVERRIDE
    else Path.home() / ".trans"
)
USER_CONFIG: Path = USER_CONFIG_DIR / "config.json"
USER_HISTORY: Path = USER_CONFIG_DIR / "history.json"


def ensure_user_dir() -> Path:
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return USER_CONFIG_DIR
