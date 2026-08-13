"""端到端：FastAPI HTTP 层测试。"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def app_module(monkeypatch, tmp_path):
    """把 translator.config 重定向到临时目录，再返回 FastAPI app。"""
    monkeypatch.setenv("TRANS_USER_DIR", str(tmp_path))
    import importlib
    for mod in ("translator.paths", "translator.settings", "translator.config",
                "translator.service", "translator.installer", "translator.api"):
        if mod in sys.modules:
            importlib.reload(sys.modules[mod])
    from translator.api import app  # noqa
    return app


@pytest.mark.asyncio
async def test_status_basic(app_module, monkeypatch):
    """engine_installed 取决于环境，断言它返回的是 bool 就够了。"""
    transport = ASGITransport(app=app_module)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/status")
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == "0.2.0"
    assert body["has_config"] is False
    assert isinstance(body["engine_installed"], bool)


@pytest.mark.asyncio
async def test_status_engine_installed_reflects_truth(app_module, monkeypatch):
    """force-engine-not-installed → status 必须如实报 False。

    这是为了守住 PYTHONPATH 修复：验证逻辑不能因为别的环境因素误报 True。
    """
    from translator import installer
    monkeypatch.setattr(installer, "is_engine_installed", lambda: False)
    # 让 api 拿到的是 monkeypatch 过的版本
    from translator import api as api_mod
    monkeypatch.setattr(api_mod.installer, "is_engine_installed", lambda: False)
    transport = ASGITransport(app=app_module)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/status")
    assert r.status_code == 200
    assert r.json()["engine_installed"] is False


@pytest.mark.asyncio
async def test_settings_save_and_masked_echo(app_module):
    transport = ASGITransport(app=app_module)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/settings", json={"api_key": "sk-secret", "target_lang": "ENG"})
        assert r.status_code == 200
        masked = r.json()
        assert masked["api_key"] == "***"
        assert masked["target_lang"] == "ENG"

        # 再读应当仍为 ***
        r2 = await c.get("/api/settings")
        assert r2.json()["api_key"] == "***"


@pytest.mark.asyncio
async def test_translate_rejects_when_no_engine(app_module):
    transport = ASGITransport(app=app_module)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        # 没装引擎 → 直接 412
        r = await c.post("/api/translate", json={"folder": "D:/no/such/path"})
        # 412（Precondition Failed）或者 400（folder 不存在）都可以接受
        assert r.status_code in {400, 412}


# ---------- 预览图相关接口 ----------

# 最小合法 1x1 PNG（67 字节）
_MINI_PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108020000007e9b55"
    "350000000a49444154789c6300010000050001a1f7dab80000000049454e44ae426082"
)


@pytest.mark.asyncio
async def test_input_images_lists_png(tmp_path, app_module):
    """输入文件夹里的 png/jpg 应该被列出来，其它扩展名忽略。"""
    (tmp_path / "a.png").write_bytes(_MINI_PNG)
    (tmp_path / "b.jpg").write_bytes(_MINI_PNG)
    (tmp_path / "c.txt").write_text("ignore me")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "d.webp").write_bytes(_MINI_PNG)

    transport = ASGITransport(app=app_module)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/input-images", params={"folder": str(tmp_path)})

    assert r.status_code == 200
    files = r.json()["files"]
    names = [Path(f).name for f in files]
    assert "a.png" in names
    assert "b.jpg" in names
    assert "d.webp" in names
    assert "c.txt" not in names


@pytest.mark.asyncio
async def test_input_images_missing_folder_returns_404(app_module, tmp_path):
    transport = ASGITransport(app=app_module)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/input-images", params={"folder": str(tmp_path / "nope")})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_preview_serves_image_with_correct_mime(tmp_path, app_module):
    img = tmp_path / "ok.png"
    img.write_bytes(_MINI_PNG)
    transport = ASGITransport(app=app_module)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/preview", params={"path": str(img)})
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("image/")
    assert r.content == _MINI_PNG


@pytest.mark.asyncio
async def test_preview_rejects_non_image_extension(tmp_path, app_module):
    txt = tmp_path / "secret.txt"
    txt.write_text("should not be served")
    transport = ASGITransport(app=app_module)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/preview", params={"path": str(txt)})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_preview_missing_file_returns_404(tmp_path, app_module):
    ghost = tmp_path / "ghost.png"
    transport = ASGITransport(app=app_module)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.get("/api/preview", params={"path": str(ghost)})
    assert r.status_code == 404
