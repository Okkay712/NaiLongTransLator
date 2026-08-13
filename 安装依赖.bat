@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 正在安装 Trans 依赖到 %~dp0.venv
echo 第一次会下载 OCR/漫画翻译相关组件，请保持网络可用。
py -3 install_deps.py
pause
