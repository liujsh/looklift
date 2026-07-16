"""app.py 测试:窗口/浏览器两种呈现方式及降级逻辑（T7/T8 验收点）。

不允许真正弹窗口或开浏览器:webbrowser.open 全程 mock；webview 全程走
sys.modules 假模块/None 哨兵制造 ImportError，从不 import 真实 pywebview。
"""
from __future__ import annotations

import sys
import threading
import types
import urllib.request

import pytest

from looklift.gui import app


@pytest.fixture(autouse=True)
def _no_real_webview(monkeypatch):
    """就算测试环境恰好装了 pywebview，也确保每个测试从干净状态 import。"""
    monkeypatch.delitem(sys.modules, "webview", raising=False)


def test_window_mode_falls_back_to_browser_on_missing_pywebview(monkeypatch, capsys):
    monkeypatch.setitem(sys.modules, "webview", None)  # import webview → ImportError
    opened = {}
    monkeypatch.setattr(app.webbrowser, "open", lambda url: opened.setdefault("url", url))

    ev = threading.Event()
    rc = app.main(browser=False, port=0, _ready_event=ev)

    assert rc == 0
    assert ev.is_set()
    assert opened["url"].startswith("http://127.0.0.1:")
    out = capsys.readouterr().out
    assert "pywebview" in out


def test_browser_mode_opens_url_and_server_is_live(monkeypatch):
    opened = {}
    monkeypatch.setattr(app.webbrowser, "open", lambda url: opened.setdefault("url", url))

    ev = threading.Event()
    rc = app.main(browser=True, port=0, _ready_event=ev)

    assert rc == 0
    assert ev.is_set()
    url = opened["url"]
    assert url.startswith("http://127.0.0.1:")
    with urllib.request.urlopen(url + "api/ping", timeout=5) as resp:
        assert resp.status == 200


def test_window_mode_falls_back_to_browser_on_create_window_exception(monkeypatch, capsys):
    fake_webview = types.ModuleType("webview")

    def _boom(*args, **kwargs):
        raise RuntimeError("WebView2 runtime not found")

    fake_webview.create_window = _boom
    fake_webview.start = lambda: None
    monkeypatch.setitem(sys.modules, "webview", fake_webview)

    opened = {}
    monkeypatch.setattr(app.webbrowser, "open", lambda url: opened.setdefault("url", url))

    ev = threading.Event()
    rc = app.main(browser=False, port=0, _ready_event=ev)

    assert rc == 0
    assert ev.is_set()
    assert opened["url"].startswith("http://127.0.0.1:")
    out = capsys.readouterr().out
    assert "浏览器模式" in out
