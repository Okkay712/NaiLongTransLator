# Trans 翻译器前端实施计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 把 D:\Trans 现有的 Tkinter GUI 替换为 FastAPI + PyWebView 桌面应用，对外可发布为 GitHub Release zip。

**Architecture:**
- 后端：FastAPI (`translator/api.py`)，跑在 `127.0.0.1:8765`，SSE 推送日志和进度
- 壳：PyWebView 调系统 Edge WebView2 渲染 `frontend/`
- 配置：用户目录 `~/.trans/config.json`（脱敏 api_key）
- 引擎：保留现有 `manga-image-translator`，首次运行时按需 pip install

**Tech Stack:** Python 3.11、FastAPI、sse-starlette、uvicorn、pywebview、PyInstaller、原生 HTML/CSS/JS

**用户最终测试完再 git 提交，本计划不含 commit 步骤。**

---

## Phase 1 — FastAPI 骨架 + 静态前端 + 配置读写

### Task 1.1：目录结构和依赖

**Files:**
- Create: `D:\Trans\translator\__init__.py`
- Create: `D:\Trans\translator\paths.py`
- Create: `D:\Trans\translator\settings.py`
- Create: `D:\Trans\translator\config.py`
- Create: `D:\Trans\translator\api.py`
- Create: `D:\Trans\translator\web\__init__.py`
- Create: `D:\Trans\frontend\index.html` (placeholder)
- Create: `D:\Trans\requirements.runtime.txt`
- Modify: `D:\Trans\requirements.txt`

**Steps:**
1. 创建目录：`translator/`、`translator/web/`、`frontend/`、`tests/`
2. `requirements.runtime.txt`：写入 FastAPI、sse-starlette、uvicorn[standard]、pywebview、python-multipart、pydantic
3. `requirements.txt` 末尾追加：`-r requirements.runtime.txt`

### Task 1.2：路径与服务配置

**File:** `translator/paths.py`

```python
from pathlib import Path
import os, sys

def project_root() -> Path:
    """app.py / run.py 所在的项目根目录"""
    if getattr(sys, 'frozen', False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent

USER_CONFIG_DIR = Path(os.environ.get("TRANS_USER_DIR", Path.home() / ".trans"))
USER_CONFIG = USER_CONFIG_DIR / "config.json"
USER_HISTORY = USER_CONFIG_DIR / "history.json"

def ensure_user_dir() -> Path:
    USER_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    return USER_CONFIG_DIR
```

**File:** `translator/settings.py`

```python
import socket

HOST = "127.0.0.1"

def _free_port(preferred=8765) -> int:
    for p in range(preferred, preferred + 30):
        with socket.socket() as s:
            try:
                s.bind((HOST, p)); return p
            except OSError:
                continue
    raise RuntimeError("无法找到可用端口")

PORT = _free_port()

INSTALL_PYPI = "manga-image-translator"
CONFIG_DEFAULTS = {
    "api_key": "",
    "target_lang": "CHS",
    "translator": "deepseek",
    "font": r"C:\Windows\Fonts\simhei.ttf",
    "save_quality": 95,
    "detector": "default",
    "ocr": "48px",
    "inpainter": "default",
    "advanced_visible": False,
}
```

### Task 1.3：用户配置读写（含 API Key 脱敏）

**File:** `translator/config.py`

```python
import json, copy
from .paths import USER_CONFIG, ensure_user_dir
from .settings import CONFIG_DEFAULTS

SENSITIVE = {"api_key"}

def load() -> dict:
    ensure_user_dir()
    if not USER_CONFIG.exists():
        return copy.deepcopy(CONFIG_DEFAULTS)
    try:
        data = json.loads(USER_CONFIG.read_text(encoding="utf-8"))
    except Exception:
        return copy.deepcopy(CONFIG_DEFAULTS)
    merged = copy.deepcopy(CONFIG_DEFAULTS)
    merged.update({k: v for k, v in data.items() if k in CONFIG_DEFAULTS})
    return merged

def save(cfg: dict) -> None:
    ensure_user_dir()
    USER_CONFIG.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def masked(cfg: dict) -> dict:
    out = dict(cfg)
    for k in SENSITIVE:
        if out.get(k):
            out[k] = "***"
    return out

def add_history(folder: str, limit: int = 5) -> list[str]:
    from .paths import USER_HISTORY
    ensure_user_dir()
    hist = []
    if USER_HISTORY.exists():
        try: hist = json.loads(USER_HISTORY.read_text(encoding="utf-8")).get("recent", [])
        except Exception: pass
    hist = [folder] + [h for h in hist if h != folder]
    hist = hist[:limit]
    USER_HISTORY.write_text(json.dumps({"recent": hist}, ensure_ascii=False), encoding="utf-8")
    return hist

def get_history() -> list[str]:
    from .paths import USER_HISTORY
    if not USER_HISTORY.exists(): return []
    try: return json.loads(USER_HISTORY.read_text(encoding="utf-8")).get("recent", [])
    except Exception: return []
```

### Task 1.4：测试 config 模块

**File:** `tests/test_config.py`

```python
import os, json, tempfile
from pathlib import Path
import pytest
from translator import config

@pytest.fixture
def tmp_user_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("TRANS_USER_DIR", str(tmp_path))
    # reset module cache
    import importlib
    from translator import paths, settings
    importlib.reload(paths); importlib.reload(settings); importlib.reload(config)
    yield tmp_path
    importlib.reload(paths); importlib.reload(settings); importlib.reload(config)

def test_load_defaults_when_missing(tmp_user_dir):
    cfg = config.load()
    assert cfg["target_lang"] == "CHS"
    assert cfg["api_key"] == ""

def test_save_and_load(tmp_user_dir):
    cfg = config.load(); cfg["api_key"] = "sk-test"; cfg["target_lang"] = "ENG"
    config.save(cfg)
    assert json.loads((tmp_user_dir / "config.json").read_text())["api_key"] == "sk-test"
    assert config.load()["target_lang"] == "ENG"

def test_masked_hides_api_key(tmp_user_dir):
    cfg = config.load(); cfg["api_key"] = "sk-real"
    m = config.masked(cfg)
    assert m["api_key"] == "***"
    assert config.load()["api_key"] == "sk-real"

def test_history(tmp_user_dir):
    h = config.add_history("D:/a")
    h = config.add_history("D:/b")
    h = config.add_history("D:/a")
    assert h == ["D:/a", "D:/b"]
```

**Step:** `pytest tests/test_config.py -v` → 全部 PASS

### Task 1.5：FastAPI 应用骨架（仅 GET / 和 /api/status）

**File:** `translator/api.py`

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from . import config
from .paths import project_root

ROOT = project_root()
app = FastAPI(title="Trans 翻译器")

@app.get("/api/status")
def status():
    from .installer import is_engine_installed
    cfg = config.load()
    return {
        "has_config": bool(cfg.get("api_key")),
        "target_lang": cfg.get("target_lang"),
        "engine_installed": is_engine_installed(),
    }

FRONTEND = ROOT / "frontend"

@app.get("/")
def index():
    return FileResponse(FRONTEND / "index.html")

app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
```

**注：** install 路由先占位，等 Task 1.6 实现。

### Task 1.6：安装器 stub + 检测

**File:** `translator/installer.py`

```python
import shutil
from pathlib import Path

def is_engine_installed() -> bool:
    """检测 manga_translator 是否可 import（用项目 .venv 解释器）"""
    import subprocess, sys, os
    from .paths import project_root
    py = project_root() / ".venv" / ("Scripts" if os.name == "nt" else "bin") / "python.exe"
    if not py.exists():
        py = Path(sys.executable)
    try:
        r = subprocess.run([str(py), "-c", "import manga_translator; print('ok')"],
                           capture_output=True, text=True, timeout=10)
        return "ok" in r.stdout
    except Exception:
        return False

def install_command() -> list[str]:
    """返回 pip install 命令（待异步执行）"""
    import sys
    return [sys.executable, "-m", "pip", "install", "manga-image-translator", "ultralytics"]
```

（实际的 pip install 异步执行留到 Phase 3，这里只先返回命令）

### Task 1.7：设置 API + history API

**追加到** `translator/api.py`：

```python
from fastapi import HTTPException
from . import config as cfg_mod

@app.get("/api/settings")
def get_settings():
    return cfg_mod.masked(cfg_mod.load())

@app.post("/api/settings")
def save_settings(payload: dict):
    if not isinstance(payload, dict):
        raise HTTPException(400, "payload 必须是 dict")
    current = cfg_mod.load()
    # api_key 为 *** 时保持不变
    for k, v in payload.items():
        if k in current:
            if k == "api_key" and v == "***":
                continue
            current[k] = v
    cfg_mod.save(current)
    return cfg_mod.masked(current)

@app.get("/api/history")
def history():
    return {"recent": cfg_mod.get_history()}
```

### Task 1.8：最小前端骨架

**File:** `frontend/index.html`

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>Trans 漫画翻译器</title>
  <link rel="stylesheet" href="css/theme.css" />
  <link rel="stylesheet" href="css/app.css" />
</head>
<body>
  <header class="app-header">
    <h1>Trans 漫画翻译器</h1>
    <button id="open-settings" class="icon-btn" aria-label="设置">⚙</button>
  </header>

  <main class="app-main">
    <section id="setup-card" class="card hidden">
      <h2>首次设置</h2>
      <p class="muted">填好下面的项就可以开始翻译了。</p>
      <label>API Key
        <input id="api_key" type="password" placeholder="例如 sk-..." />
      </label>
      <label>目标语言
        <select id="target_lang">
          <option value="CHS">简体中文</option>
          <option value="CHT">繁体中文</option>
          <option value="ENG">英文</option>
          <option value="KOR">韩文</option>
        </select>
      </label>
      <label>字体路径
        <input id="font" type="text" />
      </label>
      <label>保存质量 (1-100)
        <input id="save_quality" type="number" min="1" max="100" />
      </label>
      <details id="advanced">
        <summary>高级选项</summary>
        <label>检测器 <input id="detector" type="text" /></label>
        <label>OCR <input id="ocr" type="text" /></label>
        <label>擦字器 <input id="inpainter" type="text" /></label>
      </details>
      <div class="actions">
        <button id="save-settings" class="primary">保存</button>
      </div>
    </section>

    <section id="home-card" class="card hidden">
      <h2>选择图片文件夹</h2>
      <button id="pick-folder" class="primary big">选择文件夹</button>
      <div id="recent-wrap" class="muted"></div>
    </section>
  </main>

  <script src="js/api.js"></script>
  <script src="js/settings.js"></script>
  <script src="js/app.js"></script>
</body>
</html>
```

**File:** `frontend/css/theme.css`

```css
:root {
  --bg: #f7f7f8;
  --surface: #ffffff;
  --text: #1a1a1a;
  --muted: #6b6b6b;
  --primary: #4f7cff;
  --primary-fg: #ffffff;
  --border: #e3e3e6;
  --danger: #e64545;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #1a1b1e; --surface: #26282c; --text: #f0f0f3;
    --muted: #9b9ba1; --border: #38393e;
  }
}
body { background: var(--bg); color: var(--text); margin: 0; font-family: -apple-system, "Segoe UI", system-ui, sans-serif; }
.app-header { display: flex; align-items: center; justify-content: space-between; padding: 18px 28px; border-bottom: 1px solid var(--border); background: var(--surface); }
.app-header h1 { margin: 0; font-size: 18px; font-weight: 600; }
.app-main { padding: 28px; max-width: 720px; margin: 0 auto; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 28px; }
.card h2 { margin-top: 0; font-size: 16px; }
.muted { color: var(--muted); font-size: 13px; }
.hidden { display: none; }
label { display: block; margin-bottom: 14px; font-size: 13px; }
input, select { width: 100%; box-sizing: border-box; margin-top: 6px; padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px; background: var(--bg); color: var(--text); font-size: 14px; }
button.primary { background: var(--primary); color: var(--primary-fg); border: 0; padding: 10px 18px; border-radius: 8px; cursor: pointer; font-size: 14px; }
button.primary.big { width: 100%; padding: 14px; font-size: 16px; }
button.icon-btn { background: transparent; border: 0; font-size: 22px; cursor: pointer; color: var(--text); }
.actions { margin-top: 18px; display: flex; gap: 10px; }
details { margin-top: 10px; padding: 10px; border: 1px dashed var(--border); border-radius: 6px; }
#recent-wrap { margin-top: 18px; display: flex; flex-wrap: wrap; gap: 8px; }
.recent-chip { padding: 6px 12px; border: 1px solid var(--border); border-radius: 16px; cursor: pointer; font-size: 13px; background: var(--surface); }
```

**File:** `frontend/css/app.css`

```css
.app-header h1 { letter-spacing: 0.5px; }
input:focus, select:focus { outline: 2px solid var(--primary); outline-offset: -1px; }
button.primary:disabled { opacity: 0.5; cursor: not-allowed; }
```

**File:** `frontend/js/api.js`

```javascript
const API = (() => {
  async function get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }
  async function post(path, body) {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body ?? {}),
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  }
  return {
    status: () => get('/api/status'),
    settings: () => get('/api/settings'),
    saveSettings: (payload) => post('/api/settings', payload),
    history: () => get('/api/history'),
    pickFolder: () => post('/api/pick-folder'),
  };
})();
```

**File:** `frontend/js/settings.js`

```javascript
const Settings = (() => {
  async function open() {
    const cfg = await API.settings();
    document.getElementById('api_key').value = '';
    document.getElementById('api_key').placeholder = cfg.api_key ? '(已设置，留空保持原值)' : '例如 sk-...';
    document.getElementById('target_lang').value = cfg.target_lang;
    document.getElementById('font').value = cfg.font;
    document.getElementById('save_quality').value = cfg.save_quality;
    document.getElementById('detector').value = cfg.detector;
    document.getElementById('ocr').value = cfg.ocr;
    document.getElementById('inpainter').value = cfg.inpainter;
    document.getElementById('setup-card').classList.remove('hidden');
    document.getElementById('home-card').classList.add('hidden');
  }
  async function save() {
    const payload = {
      api_key: document.getElementById('api_key').value || '***',
      target_lang: document.getElementById('target_lang').value,
      font: document.getElementById('font').value,
      save_quality: parseInt(document.getElementById('save_quality').value, 10) || 95,
      detector: document.getElementById('detector').value,
      ocr: document.getElementById('ocr').value,
      inpainter: document.getElementById('inpainter').value,
    };
    await API.saveSettings(payload);
    location.reload();
  }
  return { open, save };
})();
```

**File:** `frontend/js/app.js`

```javascript
(async () => {
  document.getElementById('open-settings').addEventListener('click', Settings.open);
  document.getElementById('save-settings').addEventListener('click', Settings.save);

  const status = await API.status();
  const recent = await API.history();
  const recentWrap = document.getElementById('recent-wrap');
  recent.recent.forEach(p => {
    const chip = document.createElement('div');
    chip.className = 'recent-chip';
    chip.textContent = p;
    chip.title = p;
    chip.onclick = () => alert('暂未接入，Phase 3 再接：' + p);
    recentWrap.appendChild(chip);
  });

  if (!status.has_config) {
    Settings.open();
  } else {
    document.getElementById('home-card').classList.remove('hidden');
  }
})();
```

### Task 1.9：picker endpoint stub

**追加到** `translator/api.py`：

```python
@app.post("/api/pick-folder")
def pick_folder():
    """Phase 1 先返回示例，后续 Phase 3 接入真实逻辑"""
    return {"path": ""}
```

### Task 1.10：手动验证 Phase 1

```bash
cd D:\Trans
.venv\Scripts\python.exe -m pip install -r requirements.runtime.txt
.venv\Scripts\uvicorn translator.api:app --port 8765
```

浏览器打开 `http://127.0.0.1:8765/`，验证：
1. 首屏显示"首次设置"卡片
2. 填表保存 → 回到首页，配置写入 `C:\Users\<你>\.trans\config.json`
3. `http://127.0.0.1:8765/api/status` 返回 `{has_config: true, ...}`
4. `GET /api/settings` 返回的 api_key 是 `***`
5. 深色模式下颜色自动切换

**通过测试:**
```bash
.venv\Scripts\pytest tests/test_config.py -v
```
→ 4 个 PASS

---

## Phase 2 — PyWebView 窗口壳

### Task 2.1：启动入口 `run.py`

**Create:** `D:\Trans\run.py`

```python
import threading
import sys
import os

def start_server():
    import uvicorn
    from translator.api import app
    from translator.settings import HOST, PORT
    uvicorn.run(app, host=HOST, port=PORT, log_level="warning", log_config={})

def open_window():
    import webview
    from translator.settings import HOST, PORT
    window = webview.create_window(
        title="Trans 漫画翻译器",
        url=f"http://{HOST}:{PORT}/",
        width=1100, height=720,
        resizable=True,
        background_color="#1a1b1e" if os.environ.get("TRANS_DARK") else "#f7f7f8",
    )
    webview.start()

def main():
    # 后台线程起 uvicorn
    t = threading.Thread(target=start_server, daemon=True)
    t.start()
    # 等端口就绪
    import time
    from translator.settings import HOST, PORT
    import socket
    for _ in range(100):
        try:
            with socket.create_connection((HOST, PORT), timeout=0.2): break
        except OSError: time.sleep(0.1)
    open_window()

if __name__ == "__main__":
    main()
```

### Task 2.2：本地测试 window

```bash
.venv\Scripts\python.exe D:\Trans\run.py
```

验证：
1. 弹一个标题为"Trans 漫画翻译器"的窗口
2. URL 自动指向 8765
3. 关窗口后进程退出
4. `http://127.0.0.1:8765/api/status` 仍然响应（因为是 daemon）

### Task 2.3：PyInstaller spec

**Create:** `D:\Trans\dev.spec`

```python
# -*- mode: python ; coding: utf-8 -*-
import sys
from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
sys.setrecursionlimit(5000)

a = Analysis(
    ['run.py'],
    pathex=[],
    binaries=[],
    datas=[('frontend', 'frontend')],
    hiddenimports=collect_submodules('uvicorn') + collect_submodules('sse_starlette') + collect_submodules('webview'),
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name='Trans', debug=False,
    bootloader_ignore_signals=False, strip=False, upx=False,
    console=False,
    icon=None,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name='Trans',
)
```

**验证（先不打包，先确认 spec 语法没问题）：**
```bash
.venv\Scripts\python.exe -m pip install pyinstaller
.venv\Scripts\python.exe -m PyInstaller --clean -y dev.spec
```

`dist/Trans/Trans.exe` 双击应能启动窗口。

---

## Phase 3 — 翻译引擎 + SSE

### Task 3.1：服务层

**Create:** `D:\Trans\translator\service.py`

```python
import asyncio, subprocess, re, uuid, json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional
from .paths import project_root
from . import config as cfg_mod

PROGRESS_RE = re.compile(r"Translating\s+(\d+)/(\d+)", re.IGNORECASE)

@dataclass
class Task:
    id: str
    folder: str
    status: str = "idle"          # idle / starting / running / done / failed / cancelled
    current: int = 0
    total: int = 0
    log: list = field(default_factory=list)
    output_path: Optional[str] = None
    process: Optional[subprocess.Popen] = None
    queue: asyncio.Queue = None
    watchers: list = field(default_factory=list)

TASKS: dict[str, Task] = {}

def build_command(folder: str, cfg: dict) -> tuple[list[str], dict]:
    import sys, os
    from .paths import project_root
    py = project_root() / ".venv" / ("Scripts" if os.name == "nt" else "bin") / "python.exe"
    if not py.exists(): py = Path(sys.executable)
    env = os.environ.copy()
    from .paths import MODELS_DEFAULT
    env["HF_HOME"] = str(project_root() / "models" / "huggingface")
    env["TRANSFORMERS_CACHE"] = str(project_root() / "models" / "huggingface" / "transformers")
    env["PYTHONIOENCODING"] = "utf-8"
    engine_cfg = {
        "translator": {"translator": cfg.get("translator"), "target_lang": cfg.get("target_lang")},
        "detector": {"detector": cfg.get("detector", "default")},
        "ocr": {"ocr": cfg.get("ocr", "48px")},
        "inpainter": {"inpainter": cfg.get("inpainter", "default")},
        "render": {"direction": "auto", "alignment": "auto"},
    }
    (project_root() / "engine_config.json").write_text(
        json.dumps(engine_cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # API key：通过环境变量注入
    if cfg.get("api_key"):
        key = cfg["api_key"]
        translator = cfg.get("translator", "deepseek")
        if translator == "deepseek":
            env["DEEPSEEK_API_KEY"] = key
        # 其它翻译器按需扩展
    cmd = [
        str(py), "-m", "manga_translator", "local", "-v", "--overwrite",
        "--model-dir", str(project_root() / "models"),
        "--font-path", cfg.get("font", r"C:\Windows\Fonts\simhei.ttf"),
        "--config-file", str(project_root() / "engine_config.json"),
        "--save-quality", str(cfg.get("save_quality", 95)),
        "-i", folder,
    ]
    return cmd, env

async def run_task(task: Task, queue: asyncio.Queue) -> None:
    task.status = "starting"
    await queue.put({"type": "status", "status": "starting"})
    cfg = cfg_mod.load()
    cmd, env = build_command(task.folder, cfg)
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            env=env, cwd=str(project_root()), text=True, bufsize=1)
    task.process = proc
    task.status = "running"
    await queue.put({"type": "status", "status": "running"})

    loop = asyncio.get_event_loop()
    while True:
        line = await loop.run_in_executor(None, proc.stdout.readline)
        if not line:
            break
        line = line.rstrip()
        task.log.append(line)
        await queue.put({"type": "log", "text": line})
        m = PROGRESS_RE.search(line)
        if m:
            task.current, task.total = int(m.group(1)), int(m.group(2))
            await queue.put({"type": "progress", "current": task.current, "total": task.total})

    rc = proc.wait()
    if task.status == "cancelling":
        task.status = "cancelled"
        await queue.put({"type": "done", "ok": False, "cancelled": True})
    elif rc == 0:
        task.status = "done"
        out = Path(task.folder)  # 默认输出目录约定待 Phase 3.x 补充
        task.output_path = str(Path(task.folder).parent / (Path(task.folder).name + "_CN"))
        await queue.put({"type": "done", "ok": True, "output_path": task.output_path})
    else:
        task.status = "failed"
        await queue.put({"type": "done", "ok": False, "rc": rc})

async def start(folder: str) -> Task:
    tid = uuid.uuid4().hex[:12]
    q: asyncio.Queue = asyncio.Queue()
    task = Task(id=tid, folder=folder, queue=q)
    TASKS[tid] = task
    asyncio.create_task(run_task(task, q))
    return task

def cancel(tid: str) -> bool:
    t = TASKS.get(tid)
    if not t or not t.process: return False
    t.status = "cancelling"
    t.process.terminate()
    return True
```

### Task 3.2：translate/cancel/stream 端点

**追加到** `translator/api.py`：

```python
from sse_starlette.sse import EventSourceResponse
from . import service

@app.post("/api/translate")
async def translate(payload: dict):
    folder = (payload or {}).get("folder", "").strip()
    if not folder or not Path(folder).exists():
        raise HTTPException(400, "文件夹不存在")
    # 同时只跑一个
    if any(t.status in {"starting", "running"} for t in service.TASKS.values()):
        raise HTTPException(409, "已有任务在进行中，请先取消或等待")
    task = await service.start(folder)
    return {"task_id": task.id}

@app.post("/api/cancel/{task_id}")
def cancel_task(task_id: str):
    ok = service.cancel(task_id)
    return {"ok": ok}

@app.get("/api/stream/{task_id}")
async def stream(task_id: str):
    task = service.TASKS.get(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    queue = task.queue

    async def gen():
        yield {"event": "hello", "data": json.dumps({"task_id": task_id})}
        while True:
            msg = await queue.get()
            yield {"event": msg.get("type", "msg"), "data": json.dumps(msg)}
            if msg.get("type") == "done":
                break

    return EventSourceResponse(gen())
```

`json` 需要 import：`import json`

### Task 3.3：前端 - 任务页 + 跳页

**Modify:** `frontend/index.html`：把"最近使用 chip 点击"改为跳转

**Modify:** `frontend/js/app.js`：

```javascript
// 添加：选择文件夹按钮 → 后端弹原生文件夹选择框 → 拿到路径 → 跳转 task.html?folder=...
document.getElementById('pick-folder').addEventListener('click', async () => {
  const r = await API.pickFolder();
  if (r.path) {
    location.href = '/task.html?folder=' + encodeURIComponent(r.path);
  }
});
```

**Modify:** `translator/api.py`：

```python
from pathlib import Path
import platform, subprocess

@app.post("/api/pick-folder")
def pick_folder():
    if platform.system() != "Windows":
        # 其它平台留给 Phase 4；先用 input()
        return {"path": input("输入文件夹路径：").strip().strip('"')}
    try:
        # PowerShell COM 弹原生窗口
        ps = (
            "Add-Type -AssemblyName System.Windows.Forms | "
            "Out-Null; "
            "$f = New-Object System.Windows.Forms.FolderBrowserDialog; "
            "$f.Description = '选择图片文件夹'; "
            "if ($f.ShowDialog() -eq 'OK') { Write-Output $f.SelectedPath }"
        )
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=120)
        path = r.stdout.strip()
        return {"path": path}
    except Exception as e:
        raise HTTPException(500, str(e))
```

**Create:** `frontend/task.html`

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <title>翻译任务</title>
  <link rel="stylesheet" href="css/theme.css" />
  <link rel="stylesheet" href="css/app.css" />
  <style>
    .grid { display: grid; grid-template-columns: 3fr 2fr; gap: 16px; }
    .log { background: #0d0e10; color: #d0d0d4; padding: 12px; border-radius: 8px; height: 480px; overflow-y: auto; font-family: ui-monospace, Consolas, monospace; font-size: 12px; line-height: 1.5; white-space: pre-wrap; }
    .progress { font-size: 13px; }
    .progress-bar { background: var(--border); border-radius: 6px; height: 10px; overflow: hidden; margin-top: 6px; }
    .progress-bar > div { background: var(--primary); height: 100%; transition: width .3s; }
    .preview { margin-top: 14px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
    .preview img { width: 100%; border: 1px solid var(--border); border-radius: 6px; }
    .actions { margin-top: 14px; display: flex; gap: 10px; }
  </style>
</head>
<body>
  <header class="app-header">
    <h1 id="title">翻译任务</h1>
    <a href="/" class="icon-btn" aria-label="返回">←</a>
  </header>
  <main class="app-main" style="max-width: 1100px;">
    <div class="grid">
      <section class="card">
        <h2>日志</h2>
        <div id="log" class="log"></div>
      </section>
      <section class="card">
        <h2>进度</h2>
        <div class="progress"><span id="progress-text">等待启动...</span></div>
        <div class="progress-bar"><div id="progress-fill" style="width:0%"></div></div>
        <div class="preview">
          <div><div class="muted">原图</div><img id="orig" /></div>
          <div><div class="muted">译图</div><img id="trans" /></div>
        </div>
        <div class="actions">
          <button id="start" class="primary">开始翻译</button>
          <button id="cancel" class="primary" style="background: var(--danger);" disabled>取消</button>
        </div>
        <div id="result" class="muted" style="margin-top: 12px;"></div>
      </section>
    </div>
  </main>
  <script src="js/api.js"></script>
  <script src="js/task.js"></script>
</body>
</html>
```

**Create:** `frontend/js/task.js`

```javascript
(function () {
  const params = new URLSearchParams(location.search);
  const folder = params.get('folder') || '';
  document.getElementById('title').textContent = '翻译 - ' + (folder || '未选择');
  if (!folder) location.href = '/';

  const logEl = document.getElementById('log');
  const progText = document.getElementById('progress-text');
  const progFill = document.getElementById('progress-fill');
  const resultEl = document.getElementById('result');
  const startBtn = document.getElementById('start');
  const cancelBtn = document.getElementById('cancel');

  function appendLog(text) {
    const div = document.createElement('div');
    div.textContent = text;
    logEl.appendChild(div);
    logEl.scrollTop = logEl.scrollHeight;
  }

  async function start() {
    startBtn.disabled = true;
    cancelBtn.disabled = false;
    resultEl.textContent = '';
    try {
      const r = await API.startTranslate({ folder });
      runStream(r.task_id);
    } catch (e) {
      resultEl.textContent = '启动失败：' + e.message;
      startBtn.disabled = false;
      cancelBtn.disabled = true;
    }
  }

  function runStream(tid) {
    const es = new EventSource('/api/stream/' + tid);
    es.addEventListener('log', e => appendLog(JSON.parse(e.data).text || ''));
    es.addEventListener('status', e => progText.textContent = '状态：' + JSON.parse(e.data).status);
    es.addEventListener('progress', e => {
      const { current, total } = JSON.parse(e.data);
      progText.textContent = `已翻译 ${current} / ${total}`;
      progFill.style.width = (current / total * 100).toFixed(1) + '%';
    });
    es.addEventListener('done', e => {
      const data = JSON.parse(e.data);
      es.close();
      cancelBtn.disabled = true;
      if (data.ok) {
        resultEl.innerHTML = '翻译完成！输出目录：<code>' + data.output_path + '</code>';
      } else if (data.cancelled) {
        resultEl.textContent = '已取消';
      } else {
        resultEl.textContent = '失败，退出码 ' + (data.rc ?? '?');
        startBtn.disabled = false;
      }
    });
  }

  startBtn.addEventListener('click', start);
  cancelBtn.addEventListener('click', async () => {
    if (!currentTid) return;
    await API.cancel(currentTid);
  });

  let currentTid = null;
  // 重写 start 函数保留 tid
  const _start = start;
  window.start = async () => {
    _start();
  };
  // 简化：把上面的 start 改写
})();
```

**注：** Phase 3 跑通后这块逻辑收紧，currentTid 用更稳妥的全局变量，避免重复定义。

### Task 3.4：手动验证 Phase 3

```bash
.venv\Scripts\python.exe -m pytest tests/ -v
.venv\Scripts\python.exe D:\Trans\run.py
```

1. 主界面点"选择文件夹" → 弹原生文件夹选择器 → 选一个含几张图的目录
2. 跳到 task.html，点"开始翻译"
3. 看到日志滚动
4. 看到进度条（如果有 Translating X/N 输出）
5. 完成后提示输出目录

如果第一次跑会因 engine 没装失败，按 Task 3.5 修复。

### Task 3.5：首次运行安装引擎

**追加到** `translator/api.py`：

```python
from .installer import install_command, is_engine_installed
import subprocess, asyncio

INSTALL_STATE = {"running": False, "queue": None}

@app.get("/api/install/stream")
async def install_stream():
    if INSTALL_STATE["queue"] is None:
        INSTALL_STATE["queue"] = asyncio.Queue()

    async def gen():
        q = INSTALL_STATE["queue"]
        while True:
            msg = await q.get()
            yield {"event": msg.get("type", "msg"), "data": json.dumps(msg)}
            if msg.get("type") == "done":
                break

    async def runner():
        if INSTALL_STATE["running"]: return
        INSTALL_STATE["running"] = True
        try:
            cmd = install_command()
            await INSTALL_STATE["queue"].put({"type": "log", "text": "执行：" + " ".join(cmd)})
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            while True:
                line = await proc.stdout.readline()
                if not line: break
                await INSTALL_STATE["queue"].put({"type": "log", "text": line.decode(errors='replace').rstrip()})
            rc = await proc.wait()
            await INSTALL_STATE["queue"].put({"type": "done", "ok": rc == 0, "rc": rc})
        finally:
            INSTALL_STATE["running"] = False

    asyncio.create_task(runner())
    return EventSourceResponse(gen())

@app.post("/api/install")
async def kick_install():
    if is_engine_installed():
        return {"ok": True, "already": True}
    INSTALL_STATE["queue"] = asyncio.Queue()
    return {"ok": True, "started": True}
```

**Modify:** `frontend/js/app.js`：发现 status.engine_installed==false 时，弹"首次安装"提示

```javascript
if (!status.engine_installed && status.has_config) {
  if (confirm('首次运行需要安装翻译引擎（一次性，约几分钟）。现在开始？')) {
    location.href = '/install.html';
  }
}
```

**Create:** `frontend/install.html`（最小安装日志展示页，参考 task.html 的 log 区）

---

## Phase 4 — 打包收尾

### Task 4.1：spec 校准

**验证 dev.spec：**

1. 删除 `dist/`、`build/`
2. `pyinstaller --clean -y dev.spec`
3. `dist/Trans/Trans.exe` 双击运行 → 窗口弹出
4. 第一次运行会跳到 install.html → 装引擎 → 完成后能正常翻译

### Task 4.2：资源打包验证

1. 修改 `frontend/index.html` 加一行 `<p>BUILD_MARK</p>`
2. 重打包
3. 运行后看到 `BUILD_MARK` → 静态资源被打进
4. 删掉标记，重打包

### Task 4.3：发布 zip

```bash
cd dist
Compress-Archive -Path Trans -DestinationPath Trans-v0.1.0.zip -Force
```

### Task 4.4：README 更新

在 D:\Trans\README.md 末尾追加：

```markdown
## 新版本（GUI 重做）

以 EXE 分发：

1. 下载 `Trans-v0.x.x.zip` 解压
2. 双击 `Trans.exe`
3. 首次启动会让你填 API Key 并自动装翻译引擎

老版本 CLI：`python app.py <folder>` 仍然可用。
```

### Task 4.5：smoke test

```bash
pytest tests/ -v
dist/Trans/Trans.exe
# 选一个 1 张测试图，跑完确认有译图输出
```

---

## 验证清单（所有阶段都要过的）

- [ ] `pytest tests/ -v` 全 PASS
- [ ] `dev.spec` 打包能产出 `dist/Trans/Trans.exe`
- [ ] `Trans.exe` 启动后能在窗口里：
  - 保存配置（含 API Key 写入 `~/.trans/`）
  - 选择文件夹
  - 启动翻译看到实时日志
  - 看到进度条更新
  - 完成/失败/取消 三种结束状态都能显示
- [ ] `~/.trans/config.json` 的 `api_key` 字段在 API 返回里始终是 `***`

## YAGNI 边界（不在本次实施）

- 多翻译器 UI 切换（后端已预留，前端只暴露单 Key 字段）
- 拖拽上传
- 多任务并行
- 自动更新
- macOS/Linux 适配
