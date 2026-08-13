# 奶龙翻译器 漫画图片自动翻译器

一个本地批量图片翻译工具。选择包含 jpg/png/webp 的文件夹，自动识别日文文本、翻译成简体中文、擦掉原文、把中文嵌回原来的对白区域，最后输出一个新文件夹。

提供两种使用方式：
- **新：** Web 风格桌面程序（FastAPI + PyWebView），实时日志 + 进度 + 原图/译图并排预览。
- **旧（仍可用）：** Tkinter 极简 GUI + 命令行。

---

## 第一次使用（Web 风格，推荐）

### 方式 A：开发模式（直接跑源码）

```bash
# 在项目根目录下：
python -m venv .venv          # 如果还没有
.venv\Scripts\python.exe -m pip install -r requirements.runtime.txt
.venv\Scripts\python.exe install_deps.py
# 上述会拉漫画翻译引擎和它的依赖，约几分钟。
.venv\Scripts\python.exe run.py
```

会弹出标题为「奶龙翻译器」的窗口，第一次启动会引导你填 API Key，并自动安装翻译引擎。

### 方式 B：双击 `启动翻译器.bat`

保持你熟悉的入口。脚本会调 `run.py`。

### 方式 C：分发版本（打包后）

`dist/Trans/Trans.exe` 已通过 `dev.spec` 打包验证。分发时把 `dist/Trans/` 整个目录打成 zip 发布即可。

```bash
.venv\Scripts\python.exe -m PyInstaller -y dev.spec
# 产物：dist\Trans\Trans.exe（含 _internal/）
```

> 注意：首次运行 EXE 时，应用内的「安装引擎」流程会通过 pip 拉漫画翻译引擎。PyInstaller 默认没有把 pip 打进包（pip 太重），打包分发需要把 pip 也带进来或用户本机已装好 Python（当前我们走的是前者）。详见 `docs/plans/2026-08-12-trans-translator-frontend-impl.md` 第 4 阶段的 Task 4.x。

---

## 平时使用

1. 双击 `Trans.exe`（或 `启动翻译器.bat`）
2. 主页点「选择文件夹开始翻译」 → 选图片文件夹 → 跳转任务页
3. 点「开始翻译」 → 看实时日志滚动 + 进度条
4. 完成后右下角出现输出目录路径

翻译输出放在输入文件夹旁边，名字形如 `原文件夹名_CN`。

---

## 旧 GUI（兼容）

```bash
.venv\Scripts\python.exe app.py
```

会开 Tkinter 选文件夹对话框。命令行模式：

```bash
.venv\Scripts\python.exe app.py "D:\你的图片文件夹"
```

---

## 配置

Web 风格前端把配置存在用户目录下：`C:\Users\<你>\.trans\config.json`。

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

- `api_key`：每次只在「设置」页里填，前端读到的总是 `***`，落盘存真值。
- `output_mode`：`input`（与输入文件夹同目录，输出 `<输入>_CN`）/ `custom`（统一放 `output_dir`）
- `output_dir`：自定义输出目录；留空时回退到 `~/Trans_Output`。
- 想换翻译器：改 `translator` 字段（`youdao` / `baidu` / `deepl` / `chatgpt` / `none`）。
- 翻译器之外的引擎参数（detector/ocr/inpainter）可在前端「设置」→ 展开「高级选项」修改。

## 批量翻译

主页下方"批量翻译多个文件夹"展开：
- 点 **"添加一个文件夹"** 多次，累加到批次列表
- 列表里每个都可单独移除
- 点 **"开始批量"**：依次翻译，结果统一进配置好的输出目录
- 翻译过程中主页会显示实时队列状态，可点 **"查看队列详情"** → 批量页

并行只跑一个，保证显存/内存不爆。批量启动后任何环节点"取消当前"只停当前任务，后面继续。

## 翻译方式

默认用上游的 `manga-image-translator` 引擎做文字检测 → OCR → 擦除 → 翻译 → 嵌字。目标语言简体中文。

## 常见问题

- **第一次运行慢**：正常，模型会下载到 `models/`。
- **翻译失败**：多数是网络翻译接口或模型下载失败；等几分钟重新翻译即可。
- **只想识别原文**：`translator` 设为 `none`。
- **打包后找不到前端**：打包后 PyInstaller 把 `frontend/` 放在 `_internal/frontend/`，前端代码已经处理好。

## 架构和测试

```
项目根目录\
├── translator/    # FastAPI 后端
│   ├── api.py
│   ├── service.py       # 翻译任务调度（subprocess + asyncio.Queue）
│   ├── installer.py     # 引擎安装
│   ├── config.py        # ~/.trans/config.json 读写（含 api_key 脱敏）
│   ├── settings.py      # 端口和默认值
│   └── paths.py
├── frontend/      # 原生 HTML/CSS/JS（不引入 npm）
├── tests/         # pytest
├── docs/plans/    # 设计稿 + 实施计划
├── run.py         # 启动入口（uvicorn + PyWebView）
├── dev.spec       # PyInstaller 单目录 spec
└── requirements.runtime.txt
```

跑测试：

```bash
.venv\Scripts\python.exe -m pytest tests/ -v
```

## License

MIT
