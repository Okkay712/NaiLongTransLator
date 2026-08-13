@echo off
chcp 65001 >nul
cd /d "%~dp0"
if "%~1"=="" (
  echo 请把图片文件夹或 zip 文件拖到这个 bat 文件上。
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo 还没有安装依赖，请先双击 安装依赖.bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" app.py "%~1"
pause
