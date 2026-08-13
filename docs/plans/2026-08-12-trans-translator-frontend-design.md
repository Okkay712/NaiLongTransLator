# Trans 翻译器前端设计

日期：2026-08-12
项目：`D:\Trans`
目标：把当前的 Tkinter 简陋 GUI 替换成"像软件一样"的桌面应用，并支持 GitHub 发布 + 用户自配 API Key。

---

## 1. 总体架构

```
┌──────────────────────────────────────────────────┐
│  Trans.exe（PyInstaller 单目录包）                │
│                                                  │
│  ┌────────────────────────────────────────────┐  │
│  │ FastAPI（后台，跑在 127.0.0.1:端口）        │  │
│  │   ├─ /api/*  REST                           │  │
│  │   ├─ /api/stream/{id}  SSE                  │  │
│  │   └─ /*  静态前端 (frontend/)               │  │
│  └────────────────────────────────────────────┘  │
│                      ▲                            │
│                      │ http                       │
│  ┌────────────────────────────────────────────┐  │
│  │ PyWebView 窗口（Edge WebView2）             │  │
│  │   加载 http://127.0.0.1:端口/                │  │
│  │   用户看到的就是这里                        │  │
│  └────────────────────────────────────────────┘  │
│                      ▼                            │
│  subprocess.Popen 调用 manga-image-translator     │
│   （首次运行：在 .venv 里 pip install）           │
└──────────────────────────────────────────────────┘
```

技术栈：
- **后端**：Python 3.11，FastAPI，`sse-starlette`，`uvicorn`
- **进程调度**：`asyncio` + `subprocess.Popen`
- **窗口壳**：`pywebview`（调用系统 Edge WebView2）
- **前端**：原生 HTML + CSS + JavaScript（不引入 npm），可加一点点 Vue CDN 或干脆不引入
- **打包**：PyInstaller 单目录模式
- **翻译引擎**：保留现有的 `manga-image-translator`，运行时按需安装到 `.venv/`

---

## 2. 目录结构

```
D:\Trans\
├── app.py                     # 旧入口，保留 CLI 兼容
├── translator/
│   ├── __init__.py
│   ├── api.py                 # FastAPI 路由
│   ├── service.py             # 翻译任务调度（异步）
│   ├── config.py              # 用户配置 (~/.trans/config.json)
│   ├── settings.py            # 服务端配置（端口、模型目录等）
│   ├── installer.py           # 首次运行安装 manga-image-translator
│   └── paths.py               # 路径工具
├── frontend/
│   ├── index.html             # 设置 / 主选择界面
│   ├── task.html              # 任务详情（日志+进度）
│   ├── css/
│   │   ├── theme.css          # 暗色/亮色变量
│   │   └── app.css
│   └── js/
│       ├── api.js             # fetch + EventSource 封装
│       ├── settings.js        # 设置页逻辑
│       └── task.js            # 任务页逻辑
├── engine/                    # 现有 manga-image-translator 源码保留
├── models/                    # 模型缓存（首次运行时下载）
├── work/                      # 临时工作目录
├── config.json                # 默认配置（保留兼容）
├── requirements.txt           # 现有 + 新增 (fastapi, sse-starlette, pywebview, pyinstaller)
├── requirements.runtime.txt   # 运行时依赖（给 PyInstaller 用）
├── dev.spec                   # PyInstaller spec
├── 启动翻译器.bat             # 旧入口保留
└── 安装依赖.bat               # 旧入口保留 + 新安装流程
```

新启动入口：用户在桌面双击 `Trans.exe`，内部用 pywebview 启动；如果要重装/调试就 `python run.py`。

---

## 3. 用户首次运行流程

```
打开 EXE
  │
  ▼
查 ~/.trans/config.json 是否存在且有 api_key
  │
  ├── 否 → 弹"首次设置"对话框
  │         - API Key 输入框（单字段）
  │         - 目标语言（下拉，默认 CHS）
  │         - 字体路径（默认 C:\Windows\Fonts\simhei.ttf）
  │         - 保存质量（默认 95）
  │         - 高级项折叠（检测器/OCR/擦字器，默认 default/48px/default）
  │         保存 → 写 ~/.trans/config.json → 进入主界面
  │
  └── 是 → 直接进主界面
            │
            ▼
         查 .venv 是否装了 manga_translator
            │
            ├── 否 → 弹"安装引擎"窗口，进度条 + 日志
            │        调 pip install manga-image-translator
            │        装完 → 进入主界面
            │
            └── 是 → 进入主界面
```

---

## 4. 主界面 / 任务界面

**主界面（index.html）**：
- 顶部：标题"Trans 漫画翻译器" + 设置按钮（齿轮） + 关于
- 中间：大按钮"选择图片文件夹"（带历史下拉，最近 5 个）
- 底部：版本号

**任务界面（task.html）**：
- 左 60%：日志滚动区（自动滚到底）
- 右 40%：
  - 当前进度：`X / N` + 进度条
  - 最近一张预览（原图+译图并排，刷新）
  - 取消按钮（红色）
  - 完成后：复制输出路径、打开所在文件夹、下载 zip

---

## 5. API 设计

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/api/settings` | 读当前配置（api_key 字段脱敏） |
| POST | `/api/settings` | 保存配置 |
| GET | `/api/status` | 服务端状态：has_config / engine_installed / busy |
| POST | `/api/install` | 触发引擎安装（异步） |
| GET | `/api/install/stream` | SSE：安装日志流 |
| POST | `/api/translate` | 启动翻译任务，返回 task_id |
| GET | `/api/stream/{task_id}` | SSE：翻译日志+进度 |
| POST | `/api/cancel/{task_id}` | 取消任务 |
| GET | `/api/result/{task_id}` | 下载结果 zip |
| GET | `/api/preview/{task_id}/{idx}` | 当前处理到的原图/译图缩略图（base64 / 流） |
| GET | `/api/history` | 历史文件夹列表 |

任务状态机：
```
idle → starting → running → (cancelling | done | failed)
```

task_id 用 `uuid.uuid4().hex[:12]`。任务记录存内存 dict，进程退出即清空（结果路径单独写入 ~/.trans/history.json）。

---

## 6. 配置存储

`C:\Users\<用户>\.trans\config.json`：
```json
{
  "api_key": "sk-...",
  "target_lang": "CHS",
  "translator": "deepseek",
  "font": "C:\\Windows\\Fonts\\simhei.ttf",
  "save_quality": 95,
  "detector": "default",
  "ocr": "48px",
  "inpainter": "default",
  "advanced_visible": false
}
```

`C:\Users\<用户>\.trans\history.json`：
```json
{ "recent": ["D:/manga1", "D:/manga2"] }
```

**敏感字段**（api_key）在 API 返回时统一替换为 `***`。前端要修改时由用户重新输入，不回显原值。

---

## 7. 引擎调用

包装现有 `run_engine()`：
```python
async def run_translate_task(task_id, input_folder, cfg, queue):
    proc = subprocess.Popen(
        [sys.executable, "-m", "manga_translator", "local",
         "-v", "--overwrite", ...],
        stdout=PIPE, stderr=STDOUT,
        cwd=ROOT, env=env
    )
    TASKS[task_id]["process"] = proc
    async for line in proc.stdout:           # 按行
        await queue.put({"type": "log", "text": line})
        if m := re.search(r"Translating (\d+)/(\d+)", line):
            await queue.put({"type": "progress", "current": m[1], "total": m[2]})
    rc = proc.wait()
    await queue.put({"type": "done", "ok": rc == 0, "output_path": ...})
```

进度条：直接信引擎日志里的 `Translating X/N`。没有更准的信源就别自己二次估算。

---

## 8. 打包

`dev.spec`：
```python
# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import copy_metadata
a = Analysis(['run.py'], datas=[
    ('frontend', 'frontend'),
], hiddenimports=['uvicorn.logging', 'sse_starlette.sse'])
pyz = PYZ(a.pure)
exe = EXE(pyz, ..., exclude_binaries=True)
coll = COLLECT(exe, a.binaries, a.datas, name='Trans', outdir='dist/Trans')
```

UI 启动入口 `run.py`：
```python
import uvicorn
import webview
from translator.api import app
from translator.settings import HOST, PORT

def start_server():
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning")
import threading
threading.Thread(target=start_server, daemon=True).start()
webview.create_window("Trans 漫画翻译器", f"http://{HOST}:{PORT}/", width=1100, height=720)
webview.start()
```

打包命令：
```bash
.venv/Scripts/python.exe -m PyInstaller dev.spec
```

发布：把 `dist/Trans/` 整个目录打 zip 传 GitHub Release。

---

## 9. 错误处理

| 情况 | 行为 |
|---|---|
| 端口被占 | 启动时探试 8765–8775，被占用换下一个；都没有就弹窗退出 |
| 引擎未装 | 主界面按钮禁用，提示安装 |
| 配置不完整 | 主界面按钮禁用，提示设置 |
| 翻译中途失败 | SSE 推送 `failed`，前端显示错误日志和"重试"按钮 |
| 用户取消 | 终止 subprocess，清理 work/stage_<ts>，标记 cancelled |
| API Key 无效 | 引擎报错后推到 SSE 前端，提示去设置页改 Key |
| 长时间无输出（10 分钟） | 子进程心跳检测，异常时强制 kill |

---

## 10. 测试

`tests/`：
- `test_config.py` - config 读写脱敏
- `test_service.py` - 任务状态机转换（mock subprocess）
- `test_installer.py` - 模拟 installer 流程
- 端到端用 1 张测试图跑一次完整翻译（smoke test）

---

## 11. 分阶段实施

1. **阶段 1**：搭 FastAPI 骨架 + 前端静态页 + 配置读写（无 PyWebView 时浏览器手动打开 `http://127.0.0.1:8765`）
2. **阶段 2**：接 PyWebView，启动 EXE 自动弹窗口
3. **阶段 3**：接翻译引擎（subprocess + SSE 推送）
4. **阶段 4**：PyInstaller 单目录打包 + 首次安装流程

每阶段完成都需要能跑通再进下一个，不混着做。

---

## 12. 范围内/外

**范围内：**
- 多页面前端（设置、首页、任务页）
- API Key 用户自管
- 单任务串行调度
- 实时日志 + 进度
- 原图/译图预览
- PyInstaller 单目录打包

**不在本次范围（YAGNI）：**
- 多任务并行
- 多翻译器同时支持（高级项只留后门）
- 上传到云端
- 自动更新
- 国际化多语言

---

## 13. 开放问题

- 是否需要"打开输出文件夹"按钮直接调用 `os.startfile()`？需要，但前端没法直接调本地程序，需要后端暴露一个 `/api/open` 接口转 exec。
- 字体路径默认给 windows 字体目录，但跨平台怎么办？本版本只支持 Windows，先不考虑。
