"""GUI 启动器：解析 --browser/--port，起本地 server，选窗口或浏览器分支。

只做「起 server → 选前端呈现方式」，不写路由/业务逻辑（业务逻辑在 api.py）。
默认窗口模式（pywebview）；未安装 pywebview 或窗口启动失败（如 WebView2 缺失）时
自动降级为浏览器模式，不崩溃退出。
"""
from __future__ import annotations

import threading
import webbrowser

from . import server as gui_server


def main(
    browser: bool = False,
    port: int = 0,
    *,
    _ready_event: threading.Event | None = None,
) -> int:
    """启动本地 server，再按 `browser` 选窗口模式或系统浏览器模式。

    `_ready_event`：测试钩子。非 None 时，一旦本地 URL 就绪即 `set()` 并立即
    返回（不阻塞 webview.start()/事件循环），供测试注入停止点；生产路径不传。
    """
    srv = gui_server.create_server(port=port)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    actual_port = srv.server_address[1]
    url = f"http://127.0.0.1:{actual_port}/"

    if browser:
        return _run_browser(srv, url, _ready_event=_ready_event)
    return _run_window(srv, url, _ready_event=_ready_event)


def _run_window(srv, url: str, *, _ready_event: threading.Event | None) -> int:
    """窗口模式：`import webview` 失败或启动异常都自动降级为浏览器模式。"""
    try:
        import webview
    except ImportError:
        print('未安装 pywebview，请 pip install "looklift[gui]"；正在改用浏览器模式')
        return _run_browser(srv, url, _ready_event=_ready_event)

    try:
        webview.create_window("looklift", url)
        if _ready_event is not None:  # 测试钩子：不真正进入 webview 事件循环
            _ready_event.set()
            srv.shutdown()
            return 0
        webview.start()
    except Exception:  # noqa: BLE001 —— 任何窗口组件异常（如 WebView2 缺失）都降级，不崩溃
        print("窗口组件不可用，自动改用浏览器模式打开")
        return _run_browser(srv, url, _ready_event=_ready_event)

    srv.shutdown()  # 窗口已关闭，回收本地 server
    return 0


def _run_browser(srv, url: str, *, _ready_event: threading.Event | None) -> int:
    """浏览器模式：打开系统浏览器，阻塞直到 Ctrl-C。"""
    webbrowser.open(url)
    print(f"looklift 已在浏览器中打开：{url}")
    print("按 Ctrl-C 退出")

    if _ready_event is not None:  # 测试钩子：URL 就绪即返回，不阻塞
        _ready_event.set()
        return 0

    try:
        threading.Event().wait()  # 永不被 set，只能被 KeyboardInterrupt 打断
    except KeyboardInterrupt:
        pass
    srv.shutdown()
    srv.server_close()
    return 0
