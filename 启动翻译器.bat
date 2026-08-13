@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo 还没有安装依赖，请先双击 安装依赖.bat
  pause
  exit /b 1
)
echo 启动 Trans 漫画翻译器...
".venv\Scripts\python.exe" run.py
