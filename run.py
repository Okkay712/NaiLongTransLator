"""奶龙翻译器 启动入口。

行为：
1. 用一个后台线程启动 FastAPI/uvicorn（阻塞 8765 之前的空闲端口）
2. 主线程启动 PyWebView 窗口，加载本地 URL
3. 用户关闭窗口时 webview.start() 返回，后台线程自然退出（daemon=True）

打包后：sys.frozen 为 True，项目根切到 exe 所在目录（translator/paths.py 已处理）。
"""
from __future__ import annotations

import os
import socket
import threading
import time


# 启动 splash：WebView2 渲染期间显示，避免用户看到空白窗口以为没起来
# 多阶段进度说明，让用户清楚是"在加载"而不是"卡死"
SPLASH_HTML = """\
<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>奶龙翻译器</title>
<style>
  html,body{margin:0;height:100%;display:flex;align-items:center;justify-content:center;
    background:#f7f7f8;color:#444;font-family:system-ui,"Segoe UI",sans-serif}
  .box{text-align:center;width:340px}
  .logo{width:64px;height:64px;border-radius:14px;margin:0 auto 12px;display:block;
    box-shadow:0 2px 10px rgba(0,0,0,.12)}
  h1{font-size:18px;margin:0 0 4px;font-weight:600;color:#222}
  .sub{font-size:12px;color:#888;margin-bottom:18px}
  .bar{height:6px;background:#e6e7eb;border-radius:3px;overflow:hidden;margin-bottom:10px}
  .fill{height:100%;width:30%;background:linear-gradient(90deg,#5b6cff,#7a8aff);
    border-radius:3px;animation:slide 1.4s ease-in-out infinite}
  @keyframes slide{0%{transform:translateX(-100%)}100%{transform:translateX(380%)}}
  .stage{font-size:13px;color:#444;min-height:18px}
  .spin{display:inline-block;width:10px;height:10px;border:2px solid #ddd;
    border-top-color:#5b6cff;border-radius:50%;animation:spin 1s linear infinite;
    vertical-align:-1px;margin-right:6px}
  @keyframes spin{to{transform:rotate(360deg)}}
  .hint{font-size:11px;color:#aaa;margin-top:14px}
</style></head>
<body><div class="box">
  <img class="logo" src="data:image/png;base64,__LOGO_B64__" alt="" />
  <h1>奶龙翻译器</h1>
  <div class="sub">本地服务</div>
  <div class="bar"><div class="fill"></div></div>
  <div class="stage"><span class="spin"></span><span id="stage">启动本地服务…</span></div>
  <div class="hint">首次启动加载较慢，请稍候</div>
</div>
<script>
  var stages = [
    '启动本地服务…',
    '页面渲染中…',
    '准备界面资源…',
    '即将就绪…'
  ];
  var i = 0;
  setInterval(function(){
    i = (i + 1) % stages.length;
    var el = document.getElementById('stage');
    if (el) el.textContent = stages[i];
  }, 700);
</script>
</body></html>
"""


def _wait_port(host: str, port: int, timeout: float = 5.0) -> bool:
    """等 FastAPI 起来再开窗口，避免初次访问 502。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.1)
    return False


def main() -> int:
    from translator.settings import HOST, PORT
    from translator.api import app

    import uvicorn

    config = uvicorn.Config(
        app,
        host=HOST,
        port=PORT,
        log_level="warning",
        access_log=False,
        log_config=None,
    )
    server = uvicorn.Server(config)

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    if not _wait_port(HOST, PORT, timeout=8.0):
        print(f"[奶龙翻译器] 无法连接到本地服务 {HOST}:{PORT}", flush=True)
        try:
            server.should_exit = True
        except Exception:
            pass
        return 1

    import webview

    bg = "#1a1b1e" if os.environ.get("TRANS_DARK") else "#f7f7f8"
    # splash 里嵌入 logo：优先取 frontend/favicon.png（开发/frozen 均可找到）
    splash_html = SPLASH_HTML
    try:
        from translator.paths import frozen_data_dir, project_root
        fav = project_root() / "frontend" / "favicon.png"
        if not fav.exists():
            fd = frozen_data_dir()
            if fd:
                fav = fd / "frontend" / "favicon.png"
        if fav.exists():
            import base64
            b64 = base64.b64encode(fav.read_bytes()).decode("ascii")
            splash_html = SPLASH_HTML.replace("__LOGO_B64__", b64)
    except Exception:
        pass

    # 先用 splash HTML 占位，避免 WebView2 渲染空白；服务起来后切到真 URL
    win = webview.create_window(
        title="奶龙翻译器",
        html=splash_html,
        width=1100,
        height=720,
        min_size=(900, 600),
        resizable=True,
        background_color=bg,
    )

    def _navigate():
        # 给 WebView2 足够时间画 splash（之前 0.2s 太短，肉眼看不到）
        time.sleep(1.0)
        try:
            win.load_url(f"http://{HOST}:{PORT}/")
        except Exception:
            pass

    threading.Thread(target=_navigate, daemon=True).start()

    try:
        webview.start()
    except KeyboardInterrupt:
        pass
    finally:
        server.should_exit = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
