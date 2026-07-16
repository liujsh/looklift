"""GUI 启动器：解析 --browser/--port，起本地 server，选窗口或浏览器分支。

只做「起 server → 选前端呈现方式」，不写路由/业务逻辑（业务逻辑在 api.py）。
默认窗口模式（pywebview）；未安装 pywebview 或窗口启动失败（如 WebView2 缺失）时
自动降级为浏览器模式，不崩溃退出。
"""
from __future__ import annotations

import json
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

    不管走哪条分支、正常退出还是降级，返回前都会统一 `_stop()`（`shutdown()` +
    `server_close()`），不遗留 serve_forever 线程或占用端口。

    `_ready_event`：测试钩子，生产路径不传。语义按分支不同：
    - browser 分支：`webbrowser.open()` 调用之后、收尾之前 `set()`，随即收尾并
      返回——此时 server 仍在跑，测试如需验证连通性，应在 mock 的
      `webbrowser.open()` 内部同步发起请求（此时必然早于收尾），而不是等
      `main()` 返回后再查。
    - window 分支：`webview.create_window()` 成功后、真正调用
      `webview.start()` 之前 `set()`——因为生产环境 `webview.start()` 会阻塞到
      窗口关闭，钩子本身不跳过这次调用；测试用的 `webview` 桩必须避免真正阻塞
      （例如直接返回，或抛异常以复现 WebView2 故障），否则会挂住。
    """
    srv = gui_server.create_server(port=port)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    actual_port = srv.server_address[1]
    url = f"http://127.0.0.1:{actual_port}/"

    if browser:
        return _run_browser(srv, url, _ready_event=_ready_event)
    return _run_window(srv, url, _ready_event=_ready_event)


def _stop(srv) -> None:
    """统一收尾：所有退出路径都要 `shutdown()` + `server_close()`，不留残余。"""
    srv.shutdown()
    srv.server_close()


def _run_window(srv, url: str, *, _ready_event: threading.Event | None) -> int:
    """窗口模式：`import webview` 失败或启动异常都自动降级为浏览器模式。"""
    try:
        import webview
    except ImportError:
        print('未安装 pywebview，请 pip install "looklift[gui]"；正在改用浏览器模式')
        return _run_browser(srv, url, _ready_event=_ready_event)

    try:
        window = webview.create_window("looklift", url)
        _register_drop_bridge(window)
        if _ready_event is not None:  # 测试钩子：在真正调用 webview.start() 之前 set
            _ready_event.set()
        webview.start()
    except Exception:  # noqa: BLE001 —— 任何窗口组件异常（如 WebView2 缺失）都降级，不崩溃
        print("窗口组件不可用，自动改用浏览器模式打开")
        return _run_browser(srv, url, _ready_event=_ready_event)

    _stop(srv)  # 窗口已关闭，回收本地 server
    return 0


def _register_drop_bridge(window) -> None:
    """按 design.md 决策 4 注册 pywebview 原生拖放桥。

    `window.dom.document.events.drop` 是 pywebview 的 DOM 事件桥；收到的
    `event['dataTransfer']['files'][i]` 里如果带 `pywebviewFullPath`（pywebview
    专为拖放场景加的扩展字段，标准浏览器 JS 侧的 `File` 对象没有这个、出于
    安全限制拿不到真实文件系统路径），就是我们要的绝对路径。拿到路径后用
    `window.evaluate_js` 回推给前端 `App.onNativeDrop`，触发和「点击选择文件」
    一样的 JS 流程，全程不拷贝原图。

    pywebview 不同版本的 DOM 事件桥 API 有细微差异（本身就是相对新的扩展
    能力），整体包一层 try/except：注册失败只打印中文提示、优雅降级——
    window 模式下浏览器式的 `/api/upload` 上传依然可用，不影响窗口正常打开。
    """
    try:
        def _on_drop(event: dict) -> None:
            files = ((event or {}).get("dataTransfer") or {}).get("files") or []
            paths = [f["pywebviewFullPath"] for f in files if "pywebviewFullPath" in f]
            if not paths:
                return
            window.evaluate_js(f"App.onNativeDrop({json.dumps(paths)})")

        window.dom.document.events.drop += _on_drop
    except Exception:  # noqa: BLE001 —— pywebview API 版本差异一律归为「降级」，不崩溃
        print("原生拖放桥注册失败，窗口内拖拽将退回浏览器式上传")


def _run_browser(srv, url: str, *, _ready_event: threading.Event | None) -> int:
    """浏览器模式：打开系统浏览器，阻塞直到 Ctrl-C。"""
    webbrowser.open(url)
    print(f"looklift 已在浏览器中打开：{url}")
    print("按 Ctrl-C 退出")

    if _ready_event is not None:  # 测试钩子：URL 就绪即收尾并返回，不阻塞
        _ready_event.set()
        _stop(srv)
        return 0

    try:
        threading.Event().wait()  # 永不被 set，只能被 KeyboardInterrupt 打断
    except KeyboardInterrupt:
        pass
    _stop(srv)
    return 0
