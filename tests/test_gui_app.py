"""app.py 测试:窗口/浏览器两种呈现方式及降级逻辑（T7/T8 验收点）。

不允许真正弹窗口或开浏览器:webbrowser.open 全程 mock；webview 全程走
sys.modules 假模块/None 哨兵制造 ImportError，从不 import 真实 pywebview。

每个用例都要确认 `main()` 返回后不遗留 serve_forever 的 server 线程/端口
（收尾契约见 app.py 的 `_stop()`），用 `threading.active_count()` 前后比对。
"""
from __future__ import annotations

import sys
import threading
import time
import types
import urllib.request

import pytest

from looklift.gui import app


@pytest.fixture(autouse=True)
def _no_real_webview(monkeypatch):
    """就算测试环境恰好装了 pywebview，也确保每个测试从干净状态 import。"""
    monkeypatch.delitem(sys.modules, "webview", raising=False)


def _assert_no_leaked_threads(before_count: int) -> None:
    """允许收尾中的瞬时线程有一点时间退出，最终活跃线程数不应超过调用前。"""
    for _ in range(20):
        if threading.active_count() <= before_count:
            return
        time.sleep(0.05)
    assert threading.active_count() <= before_count


def test_window_mode_falls_back_to_browser_on_missing_pywebview(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "webview", None)  # import webview → ImportError
    opened = {}
    monkeypatch.setattr(app.webbrowser, "open", lambda url: opened.setdefault("url", url))

    before = threading.active_count()
    ev = threading.Event()
    rc = app.main(browser=False, port=0, _ready_event=ev)

    assert rc == 0
    assert ev.is_set()
    assert opened["url"].startswith("http://127.0.0.1:")
    out = capsys.readouterr().out
    assert "pywebview" in out
    _assert_no_leaked_threads(before)


def test_browser_mode_opens_url_and_server_is_live_before_shutdown(monkeypatch):
    """`webbrowser.open()` 被调用的那一刻 server 必须已在跑（收尾发生在它之后），
    `main()` 返回后 server 必须已完全收尾。用 mock 的 `open()` 在调用瞬间同步发
    请求做连通性检查，避免另起线程去 race 收尾的 shutdown/close 时序。
    """
    captured = {}

    def _fake_open(url: str) -> None:
        captured["url"] = url
        with urllib.request.urlopen(url + "api/ping", timeout=5) as resp:
            captured["status"] = resp.status

    monkeypatch.setattr(app.webbrowser, "open", _fake_open)

    before = threading.active_count()
    ev = threading.Event()
    rc = app.main(browser=True, port=0, _ready_event=ev)

    assert rc == 0
    assert ev.is_set()
    assert captured["url"].startswith("http://127.0.0.1:")
    assert captured["status"] == 200
    _assert_no_leaked_threads(before)


class _FakeDropEvents:
    """模拟 pywebview `window.dom.document.events.drop`：`+=` 订阅一个 handler。"""

    def __init__(self) -> None:
        self.subscribed = None

    def __iadd__(self, handler):
        self.subscribed = handler
        return self


class _FakeDom:
    def __init__(self) -> None:
        self.document = types.SimpleNamespace(events=types.SimpleNamespace(drop=_FakeDropEvents()))


class _FakeLoadedEvent:
    """模拟 pywebview `window.events.loaded`：`+=` 订阅一个 handler。"""

    def __init__(self) -> None:
        self.subscribed = None

    def __iadd__(self, handler):
        self.subscribed = handler
        return self


class _FakeWindowWithDrop:
    def __init__(self) -> None:
        self.dom = _FakeDom()
        self.events = types.SimpleNamespace(loaded=_FakeLoadedEvent())
        self.evaluate_js_calls = []

    def evaluate_js(self, script: str) -> None:
        self.evaluate_js_calls.append(script)


def test_register_drop_bridge_subscribes_and_forwards_pywebview_full_path():
    """决策 4：注册 `window.dom.document.events.drop`，收到事件后只转发带
    `pywebviewFullPath` 的文件，通过 `evaluate_js` 回推 `App.onNativeDrop`。"""
    window = _FakeWindowWithDrop()

    app._register_drop_bridge(window)

    assert window.dom.document.events.drop.subscribed is not None

    event = {
        "dataTransfer": {
            "files": [
                {"pywebviewFullPath": "C:\\Users\\me\\a.jpg", "name": "a.jpg"},
                {"name": "no-native-path.jpg"},  # 标准浏览器 File，没有这个扩展字段
            ]
        }
    }
    window.dom.document.events.drop.subscribed(event)

    drop_calls = [c for c in window.evaluate_js_calls if c.startswith("App.onNativeDrop(")]
    assert len(drop_calls) == 1
    assert "a.jpg" in drop_calls[0]
    assert "no-native-path.jpg" not in drop_calls[0]


def test_register_drop_bridge_subscribes_loaded_event_and_sets_ready_flag_on_fire():
    """代码评审修订：不再用耗时猜测式的去重，改成页面 `loaded` 事件后在 JS 侧
    打一个同步标记 `window.__looklift_native_drop_ready = true`，前端
    `bindDropzone` 同步读这个标记区分 window/browser 模式。`loaded` 事件本身
    只在 `create_window()` 之后、页面真正加载完才触发，这里模拟"触发"这一步，
    确认注册的 handler 调用时会 evaluate_js 这段标记脚本。"""
    window = _FakeWindowWithDrop()

    app._register_drop_bridge(window)

    assert window.events.loaded.subscribed is not None

    window.events.loaded.subscribed()  # 模拟 pywebview 触发 loaded 事件

    ready_calls = [c for c in window.evaluate_js_calls if "__looklift_native_drop_ready" in c]
    assert len(ready_calls) == 1
    assert "true" in ready_calls[0]


def test_register_drop_bridge_degrades_gracefully_when_dom_bridge_missing(capsys):
    """pywebview API 版本差异：`window` 没有 `.dom`（旧版本/桩对象）时不应抛出，
    只打印中文提示——window 模式下浏览器式 `/api/upload` 上传依然可用。也不应
    该继续尝试注册 loaded 就绪标记（drop 桥都没建成，标记没有意义）。"""
    window = object()  # 没有 .dom 属性

    app._register_drop_bridge(window)  # 不应抛异常

    out = capsys.readouterr().out
    assert "拖" in out or "降级" in out or "失败" in out


def test_register_drop_bridge_degrades_gracefully_when_loaded_event_missing(capsys):
    """drop 桥注册成功，但 `window.events`（或 `.loaded`）在这个 pywebview
    版本上不存在——就绪标记注册失败也不该抛出，只打印中文提示；drop 桥本身
    已经生效，不受影响。"""

    class _WindowWithDropOnly:
        def __init__(self) -> None:
            self.dom = _FakeDom()
            # 故意不提供 .events

        def evaluate_js(self, script: str) -> None:
            pass

    window = _WindowWithDropOnly()

    app._register_drop_bridge(window)  # 不应抛异常

    assert window.dom.document.events.drop.subscribed is not None
    out = capsys.readouterr().out
    assert "失败" in out or "降级" in out


def test_window_mode_registers_drop_bridge_before_start(monkeypatch):
    """`_run_window` 走通路径（create_window 成功、start 正常返回）时，应该把
    创建出来的 window 对象交给 `_register_drop_bridge` 完成拖放桥 + 就绪标记
    的注册。"""
    fake_window = _FakeWindowWithDrop()
    fake_webview = types.ModuleType("webview")
    fake_webview.create_window = lambda *a, **k: fake_window
    fake_webview.start = lambda *a, **k: None  # 正常返回，不阻塞
    monkeypatch.setitem(sys.modules, "webview", fake_webview)

    before = threading.active_count()
    ev = threading.Event()
    rc = app.main(browser=False, port=0, _ready_event=ev)

    assert rc == 0
    assert ev.is_set()
    assert fake_window.dom.document.events.drop.subscribed is not None
    assert fake_window.events.loaded.subscribed is not None
    _assert_no_leaked_threads(before)


def test_window_mode_falls_back_to_browser_on_webview_start_exception(monkeypatch, capsys):
    """真实 WebView2 故障通常在 `webview.start()` 才炸（不是 `create_window()`），
    stub 还原这个更真实的失败位置，确认仍会降级到浏览器模式。"""
    fake_webview = types.ModuleType("webview")
    fake_webview.create_window = lambda *a, **k: None  # 建窗成功

    def _boom() -> None:
        raise RuntimeError("WebView2 runtime not found")

    fake_webview.start = _boom
    monkeypatch.setitem(sys.modules, "webview", fake_webview)

    opened = {}
    monkeypatch.setattr(app.webbrowser, "open", lambda url: opened.setdefault("url", url))

    before = threading.active_count()
    ev = threading.Event()
    rc = app.main(browser=False, port=0, _ready_event=ev)

    assert rc == 0
    assert ev.is_set()
    assert opened["url"].startswith("http://127.0.0.1:")
    out = capsys.readouterr().out
    assert "浏览器模式" in out
    _assert_no_leaked_threads(before)
