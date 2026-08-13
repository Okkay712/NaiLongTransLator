"""验证 installer 的关键不变量（不真跑下载/安装）。"""
from __future__ import annotations

import asyncio

from translator import installer


def test_engine_url_is_github_not_pypi():
    """engine 在 GitHub 上，不在 PyPI 上——这是 PyPI 找不到的根本原因。"""
    assert installer.ENGINE_URL.startswith("https://github.com/")
    assert "zip" in installer.ENGINE_URL


def test_is_engine_installed_returns_bool():
    assert isinstance(installer.is_engine_installed(), bool)


def test_run_install_is_async():
    assert asyncio.iscoroutinefunction(installer.run_install)


def test_engine_source_dir_path():
    p = installer.engine_source_dir()
    assert p.name == "manga-image-translator-main"
    assert p.parent.name == "engine"


def test_stripped_pins_contains_numpy():
    """numpy==1.26.4 这个 pin 会和 opencv-python-headless 4.13 打架，必须拿掉。"""
    assert "numpy" in installer.STRIPPED_PINS


def test_is_engine_installed_false_when_no_src_dir(tmp_path, monkeypatch):
    """源码目录不存在时，is_engine_installed 应该直接返回 False，不开子进程。"""
    import subprocess
    calls = []

    def fake_run(*a, **kw):
        calls.append((a, kw))
        raise AssertionError("子进程不应该被调用")

    monkeypatch.setattr(subprocess, "run", fake_run)
    monkeypatch.setattr(installer, "engine_source_dir", lambda: tmp_path / "no-such")
    assert installer.is_engine_installed() is False
    assert calls == []
