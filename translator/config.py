"""用户配置读写。所有持久化用户输入都在 ~/.trans/ 下。"""
from __future__ import annotations

import copy
import json

from .paths import USER_CONFIG, USER_HISTORY, ensure_user_dir
from .settings import CONFIG_DEFAULTS

# 敏感字段：API 返回时脱敏，提交保存时被空字符串/*** 视为"不修改"
SENSITIVE = {"api_key"}


def load() -> dict:
    """读 ~/.trans/config.json，缺失/损坏时返回默认值。"""
    ensure_user_dir()
    if not USER_CONFIG.exists():
        return copy.deepcopy(CONFIG_DEFAULTS)
    try:
        data = json.loads(USER_CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return copy.deepcopy(CONFIG_DEFAULTS)
    merged = copy.deepcopy(CONFIG_DEFAULTS)
    if isinstance(data, dict):
        for k, v in data.items():
            if k in CONFIG_DEFAULTS:
                merged[k] = v
    return merged


def save(cfg: dict) -> None:
    ensure_user_dir()
    USER_CONFIG.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def masked(cfg: dict) -> dict:
    """返回脱敏副本。供 API 读取时使用，避免把 api_key 漏到前端。"""
    out = dict(cfg)
    for k in SENSITIVE:
        if out.get(k):
            out[k] = "***"
    return out


def add_history(folder: str, limit: int = 5) -> list[str]:
    """追加一条历史文件夹记录，去重 + 限长。"""
    ensure_user_dir()
    hist: list[str] = []
    if USER_HISTORY.exists():
        try:
            data = json.loads(USER_HISTORY.read_text(encoding="utf-8"))
            hist = list(data.get("recent", []))
        except (OSError, ValueError):
            hist = []
    if folder:
        hist = [folder] + [h for h in hist if h != folder]
    hist = hist[:limit]
    USER_HISTORY.write_text(
        json.dumps({"recent": hist}, ensure_ascii=False),
        encoding="utf-8",
    )
    return hist


def get_history() -> list[str]:
    if not USER_HISTORY.exists():
        return []
    try:
        data = json.loads(USER_HISTORY.read_text(encoding="utf-8"))
        return list(data.get("recent", []))
    except (OSError, ValueError):
        return []
