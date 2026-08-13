# -*- mode: python ; coding: utf-8 -*-
# 单文件 EXE：所有依赖、frontend/ 都打进 Trans.exe 自身
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).resolve() if 'SPECPATH' in globals() else Path('.').resolve()

block_cipher = None
sys.setrecursionlimit(5000)

a = Analysis(
    [str(ROOT / 'run.py')],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(ROOT / 'frontend'), 'frontend')],
    hiddenimports=(
        collect_submodules('uvicorn')
        + collect_submodules('sse_starlette')
        + collect_submodules('webview')
        + collect_submodules('engineio')
        + collect_submodules('socketio')
        + ['clr_loader', 'pythonnet']
    ),
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'matplotlib', 'pandas', 'scipy'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

# onefile 模式：binaries / zipfiles / datas 全部并入 EXE
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='Trans',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,  # 不弹黑色控制台
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / 'app.ico'),
)
