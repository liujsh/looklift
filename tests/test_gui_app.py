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
