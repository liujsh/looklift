"""GUI-T10:首次配置向导后端 —— `GET/POST /api/config`。

覆盖面(design.md 风险清单「首次配置向导卡死」的验收口径):
  - `GET /api/config` 的 `configured` 判定(provider 显式配置 / 有 api_key /
    本地有 claude CLI 三选一即算"分析用得起来")；未配置时三者皆无。
  - `POST /api/config` 合并写入、空字符串 api_key 表示"保留原值"、
    provider 非法值 400。
  - 任何响应体都不得带 `api_key` 字段(即便刚写入过)。
  - index.html 静态结构:向导容器 + 表单字段名齐全。

走真实 running server（复用 test_gui_upload.py 的 fixture 写法），不 mock
server 内部路由分发；只在 `looklift.gui.api` 这个模块的 `shutil.which` 打桩，
模拟"本机没装 claude CLI"这个未配置态的第三个条件。`tests/conftest.py` 的
autouse fixture 已经把 `config.CONFIG_PATH`/`Path.home()`/`LOOKLIFT_*` 环境
变量隔离好了，这里不用重复处理。
"""
from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path

import pytest

from looklift import config
from looklift.gui import api, server as gui_server


@pytest.fixture
def running_server():
    srv = gui_server.create_server(port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def _request(srv, method: str, path: str, payload: dict | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
    try:
        body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        headers = {"Content-Type": "application/json"}
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        return resp.status, json.loads(raw)
    finally:
        conn.close()


# ─── GET /api/config ────────────────────────────────────────────────────


def test_get_config_unconfigured_when_no_provider_no_key_no_cli(running_server, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda _: None)

    status, data = _request(running_server, "GET", "/api/config")

    assert status == 200
    assert data["configured"] is False
    assert data["has_key"] is False
    assert "api_key" not in data


def test_get_config_considers_cli_on_path_as_configured(running_server, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda _: "C:\\fake\\claude.cmd")

    status, data = _request(running_server, "GET", "/api/config")

    assert status == 200
    assert data["configured"] is True


# ─── POST /api/config ───────────────────────────────────────────────────


def test_post_config_valid_merges_onto_load_config(running_server, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda _: None)

    status, data = _request(
        running_server,
        "POST",
        "/api/config",
        {"provider": "api", "model": "claude-x", "api_key": "sk-abc", "base_url": "https://example.com"},
    )

    assert status == 200
    cfg = config.load_config()
    assert cfg["provider"] == "api"
    assert cfg["model"] == "claude-x"
    assert cfg["api_key"] == "sk-abc"
    assert cfg["base_url"] == "https://example.com"


def test_get_config_after_post_is_configured_with_key_and_never_leaks_it(running_server, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda _: None)
    _request(running_server, "POST", "/api/config", {"provider": "api", "api_key": "sk-abc"})

    status, data = _request(running_server, "GET", "/api/config")

    assert status == 200
    assert data["configured"] is True
    assert data["has_key"] is True
    assert "api_key" not in data


def test_post_config_empty_api_key_keeps_existing_key(running_server, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda _: None)
    _request(running_server, "POST", "/api/config", {"provider": "api", "api_key": "sk-keep-me"})

    status, data = _request(running_server, "POST", "/api/config", {"provider": "api", "api_key": ""})

    assert status == 200
    assert config.load_config()["api_key"] == "sk-keep-me"


def test_post_config_invalid_provider_returns_400_in_chinese(running_server):
    status, data = _request(running_server, "POST", "/api/config", {"provider": "bogus"})

    assert status == 400
    assert "error" in data
    assert any("一" <= ch <= "鿿" for ch in data["error"])  # 中文错误提示


def test_post_config_partial_update_does_not_clobber_other_fields(running_server, monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda _: None)
    _request(running_server, "POST", "/api/config", {"provider": "api", "model": "claude-x"})

    status, data = _request(running_server, "POST", "/api/config", {"provider": "cli"})

    assert status == 200
    cfg = config.load_config()
    assert cfg["provider"] == "cli"
    assert cfg["model"] == "claude-x"  # 未在这次请求里出现的字段保持不变


# ─── 纯函数:analyze 是否可用 ────────────────────────────────────────────


def test_analyze_would_work_true_when_provider_explicit():
    assert api._analyze_would_work({"provider": "cli", "api_key": "", "model": "", "base_url": ""}) is True
    assert api._analyze_would_work({"provider": "api", "api_key": "", "model": "", "base_url": ""}) is True


def test_analyze_would_work_true_when_api_key_present():
    assert api._analyze_would_work({"provider": "auto", "api_key": "sk-x", "model": "", "base_url": ""}) is True


def test_analyze_would_work_false_when_nothing_available(monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda _: None)
    assert api._analyze_would_work({"provider": "auto", "api_key": "", "model": "", "base_url": ""}) is False


# ─── index.html 静态结构 ─────────────────────────────────────────────────


def _index_html_text() -> str:
    static_dir = Path(__file__).parent.parent / "looklift" / "gui" / "static"
    return (static_dir / "index.html").read_text(encoding="utf-8")


def test_index_html_has_wizard_container():
    text = _index_html_text()
    assert 'id="wizard"' in text


def test_index_html_has_wizard_skip_button():
    text = _index_html_text()
    assert 'id="wizard-skip"' in text


def test_index_html_settings_form_has_all_config_field_names():
    text = _index_html_text()
    for field_name in ("provider", "model", "api_key", "base_url"):
        assert f'name="{field_name}"' in text, f"settings 表单缺少字段:{field_name}"
