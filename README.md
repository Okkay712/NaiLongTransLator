# 奶龙翻译器 · 漫画图片自动翻译器

一个本地批量图片翻译工具：选择包含 jpg/png/webp/bmp 的文件夹，自动完成 **文字检测 → OCR → 擦除 → 翻译 → 嵌字**，把图片翻译成目标语言，输出到新文件夹。

界面是 Web 风格桌面程序（FastAPI + PyWebView），带启动画面、实时日志、进度条、原图/译图并排预览。

> 还保留旧版 Tkinter 极简 GUI（`app.py`，配合 `拖文件夹到这里翻译.bat` 可拖拽文件夹/zip 使用）。

---

## 功能特性

- 原图/译图实时预览：翻译过程中左右并排，每完成一张自动切换下一张
- 批量翻译：一次添加多个文件夹，串行执行，统一输出到配置目录；队列页实时显示每个任务状态
- 任务可取消：任务页和批量队列页都能随时取消（排队中直接取消，进行中终止子进程）
- 自定义输出位置：两种模式——与输入同目录（`<输入>_CN`），或统一输出到指定目录（默认 `~/Trans_Output`）
- 实时进度：每张图的进度条 + 日志滚动，失败/完成自动展开日志方便排查
- 主页顶部"正在进行的任务"栏目：随时看到队列状态，一键回到任务页
- 最近使用记录：主页显示历史文件夹，点击直接开始
- 完成弹窗提示输出路径，一键打开输出目录

---

## 快速开始

### 方式 A：源码运行

```bash
# 项目根目录下，一条命令完成：创建 .venv + 装运行依赖 + 从 GitHub 下载漫画翻译引擎并装依赖（约几分钟）
py -3 install_deps.py
# 启动
.venv\Scripts\python.exe run.py
```

弹出「奶龙翻译器」窗口后，第一次启动会引导你填 API Key 并安装翻译引擎。

### 方式 B：一键脚本

双击 `安装依赖.bat` 完成环境准备（等价于上面的 `install_deps.py`），之后双击 `启动翻译器.bat` 启动，也可以使用`奶龙翻译器.exe`启动。

### 方式 C：打包产物（分发用）

```bash
.venv\Scripts\python.exe -m PyInstaller -y dev_onefile.spec
# 产物：dist\Trans.exe（单文件，frontend/ 已内嵌）
```

分发时发布 `dist\Trans.exe` 即可（发布版建议改名如 `奶龙翻译器.exe`）。

> 注意：EXE 不包含翻译引擎和模型（约 5GB）。首次运行点主页「去安装」，应用会从 GitHub 下载引擎源码并安装依赖。需要网络能访问 GitHub。

---

## 使用流程

1. 打开「奶龙翻译器」（EXE 或 `启动翻译器.bat`）
2. 主页点 **「翻译一个文件夹」** 选择图片文件夹 → 进入任务页
3. 任务页左侧立即显示第一张原图
4. 点 **「开始翻译」**：
   - 每完成一张：右侧显示该张译图，左侧自动切到下一张原图
   - 顶部进度条 + 每张计数实时更新
   - 中途想停：点 **「取消」**
5. 全部完成后弹窗提示输出路径，可点 **「打开输出目录」** 直接查看
6. 想批量：主页展开 **「批量翻译多个文件夹」**，添加多个文件夹后点「开始批量」；队列详情页可看每个任务的状态、取消或打开输出目录

---

## 配置

新版 Web 界面的配置存在用户目录下：`C:\Users\<你>\.trans\config.json`（首次运行时自动创建，不会进入项目目录）。

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
  "output_mode": "custom",
  "output_dir": ""
}
```

- **api_key**：只在「设置」页填写；接口读取时永远显示 `***`，真实值只落盘在用户目录的 config.json
- **target_lang**：CHS（简体中文）/ CHT（繁体）/ ENG / KOR
- **translator**：默认 `deepseek`（需在设置页填 DeepSeek API Key，可在 platform.deepseek.com 申请）；也可改 `youdao` / `baidu` / `deepl` / `chatgpt` / `none`（none = 只识别原文，不翻译）。注意：应用内目前只支持配置 DeepSeek 的 API Key，其余翻译器选项会直接透传给引擎，按引擎默认行为工作
- **output_mode**：`custom`（默认，统一输出到 `output_dir`，留空则为 `~/Trans_Output`）/ `input`（与输入文件夹同目录，输出 `<输入>_CN`）
- **高级选项**（detector / ocr / inpainter）：在「设置」页展开「高级选项」修改

设置页可通过主页 / 任务页 / 批量页右上角 ⚙ 进入；左上角「←」返回原页面。

> 旧版 CLI（`app.py` / 拖文件夹 bat）使用**项目根目录**的 `config.json`，配置项不同（含 `zip_result`），与新 Web 界面互不影响。

---

## 翻译方式

默认使用开源引擎 [manga-image-translator](https://github.com/zyddnys/manga-image-translator)（文字检测 → OCR → 擦除 → 翻译 → 嵌字），翻译部分默认走 DeepSeek 大模型，中文质量好、便宜。

---

## 常见问题

- **第一次运行慢**：正常，引擎模型会下载到 `models/`（引擎和模型都放项目目录，不进 git）。
- **翻译失败**：多为网络问题（DeepSeek 接口或模型下载）。看日志里 `[奶龙翻译器] 子进程退出，共 N 行日志，rc=X`，rc 非 0 就是失败了。
- **只想识别原文不翻译**：`translator` 设为 `none`。
- **没有显示译图预览**：确认日志里有 `Saving "..."` 行（引擎保存图片时会打印）；预览依赖这行日志触发。
- **打包后找不到前端**：打包时 `frontend/` 已内嵌进 EXE（单文件模式运行时自动解包，单目录模式在 `_internal/frontend/`），代码已处理。

---

## 架构与测试

```
项目根目录\
├── translator/    # FastAPI 后端
│   ├── api.py         # 路由（翻译 / 取消 / 队列 / 预览 / 安装 / SSE 流）
│   ├── service.py     # 任务调度（subprocess + asyncio.Queue 串行队列，支持取消）
│   ├── installer.py   # 引擎安装（下载 GitHub 源码 + 装依赖 + import 验证）
│   ├── config.py      # ~/.trans/config.json 读写（api_key 脱敏）
│   ├── settings.py    # 端口、默认配置
│   └── paths.py       # 开发 / 打包路径解析
├── frontend/      # 原生 HTML/CSS/JS（无 npm 依赖）
│   ├── index.html     # 主页（选文件夹 / 批量 / 正在进行的任务 / 最近使用）
│   ├── task.html      # 翻译任务页（进度 + 原图/译图预览 + 取消）
│   ├── batch.html     # 批量队列页
│   ├── settings.html  # 设置页
│   ├── install.html   # 引擎安装页
│   ├── css/           # 主题与通用样式
│   └── js/            # 各页面逻辑
├── tests/         # pytest（config / service / api / installer）
├── run.py         # 启动入口（uvicorn + PyWebView，带 splash 启动画面）
├── install_deps.py    # 引擎 + 依赖一键安装（等价于 安装依赖.bat）
├── dev.spec           # PyInstaller 单目录 spec
├── dev_onefile.spec   # PyInstaller 单文件 spec（推荐分发）
└── requirements.runtime.txt
```

跑测试：

```bash
.venv\Scripts\python.exe -m pytest tests/ -v
```

---

## License

[MIT](LICENSE)
