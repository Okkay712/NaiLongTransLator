"""translator.config 模块的测试。"""
from __future__ import annotations

import importlib
import json
import sys

import pytest


@pytest.fixture
def fresh_user_dir(monkeypatch, tmp_path):
    """把 ~/.trans 重定向到 tmp_path，避免污染真实用户配置。"""
    monkeypatch.setenv("TRANS_USER_DIR", str(tmp_path))
    # 重新加载用到该目录的模块，让缓存失效
    for mod in ("translator.paths", "translator.settings", "translator.config"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    yield tmp_path


def test_load_returns_defaults_when_missing(fresh_user_dir):
    from translator import config
    cfg = config.load()
    assert cfg["target_lang"] == "CHS"
    assert cfg["api_key"] == ""
    assert cfg["save_quality"] == 95


def test_save_and_reload(fresh_user_dir):
    from translator import config
    cfg = config.load()
    cfg["api_key"] = "sk-test"
    cfg["target_lang"] = "ENG"
    cfg["save_quality"] = 80
    config.save(cfg)

    on_disk = json.loads((fresh_user_dir / "config.json").read_text(encoding="utf-8"))
    assert on_disk["api_key"] == "sk-test"
    assert on_disk["target_lang"] == "ENG"

    cfg2 = config.load()
    assert cfg2["target_lang"] == "ENG"
    assert cfg2["api_key"] == "sk-test"
    assert cfg2["save_quality"] == 80
    # 没写过的字段恢复默认
    assert cfg2["font"].endswith("simhei.ttf")


def test_masked_hides_api_key(fresh_user_dir):
    from translator import config
    cfg = config.load()
    cfg["api_key"] = "sk-real-key"
    config.save(cfg)
    masked = config.masked(cfg)
    assert masked["api_key"] == "***"
    # 原始 cfg 没有被改写
    assert cfg["api_key"] == "sk-real-key"
    # 落盘后从新读出的也是真值（脱敏只在 API 层做）
    fresh = config.load()
    assert fresh["api_key"] == "sk-real-key"


def test_history_dedup_and_limit(fresh_user_dir):
    from translator import config
    h = config.add_history("D:/a")
    assert h == ["D:/a"]
    config.add_history("D:/b")
    config.add_history("D:/c")
    config.add_history("D:/d")
    config.add_history("D:/e")
    config.add_history("D:/f")
    h = config.add_history("D:/a")
    # D:/a 应当被提到首位，保留 5 个
    assert h[0] == "D:/a"
    assert len(h) == 5
    assert h == ["D:/a", "D:/f", "D:/e", "D:/d", "D:/c"]
    # 读盘验证
    assert config.get_history()[0] == "D:/a"


def test_invalid_json_returns_defaults(fresh_user_dir):
    from translator import config
    fresh_user_dir.mkdir(parents=True, exist_ok=True)
    (fresh_user_dir / "config.json").write_text("not json", encoding="utf-8")
    cfg = config.load()
    assert cfg["target_lang"] == "CHS"
