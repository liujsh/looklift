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
import re
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


def test_get_config_considers_anthropic_api_key_env_as_configured(running_server, monkeypatch):
    """代码评审(Important):providers.get_provider("auto") 把 ANTHROPIC_API_KEY
    环境变量当成"api 可用"（providers.py:136-137，design.md §10 有文档化），
    这里的 configured 判定必须跟它口径一致——否则只用环境变量配置的用户，
    向导会每次启动都跳出来烦（违反 requirements.md 验收第 3 条"配置过一次后
    再次启动直接进主界面"）。"""
    monkeypatch.setattr(api.shutil, "which", lambda _: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env-key")

    status, data = _request(running_server, "GET", "/api/config")

    assert status == 200
    assert data["configured"] is True


def test_get_config_unconfigured_when_anthropic_api_key_env_absent(running_server, monkeypatch):
    """上一条的对照组：env 未设置时（显式 delenv，不依赖测试执行环境是否
    本来就没设），其余条件皆无 → 仍然是 false，确认 env 检查没有引入误报。"""
    monkeypatch.setattr(api.shutil, "which", lambda _: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    status, data = _request(running_server, "GET", "/api/config")

    assert status == 200
    assert data["configured"] is False


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


def test_post_config_empty_base_url_keeps_existing(running_server, monkeypatch):
    """代码评审(Must-fix，base_url 静默清空):设置表单/向导每次都提交
    `base_url: ""`（前端出于对称考虑不回填），而 `_post_config` 原本无条件
    写入任何出现的字段——导致已配好的 OpenAI 兼容代理地址（国内用户关键）
    在任何一次保存设置时被清空。要求 `base_url` 跟 `api_key` 一样吃"空字符串
    = 保留原值"的待遇。"""
    monkeypatch.setattr(api.shutil, "which", lambda _: None)
    _request(running_server, "POST", "/api/config", {"provider": "api", "base_url": "https://proxy.example.com/v1"})

    status, data = _request(running_server, "POST", "/api/config", {"provider": "api", "base_url": ""})

    assert status == 200
    assert config.load_config()["base_url"] == "https://proxy.example.com/v1"


def test_get_config_reports_on_disk_provider_model_not_env(running_server, monkeypatch):
    """代码评审(Must-fix，env 固化):`_get_config` 原本用带 env 合并的
    `load_config()` 回填表单里的 provider/model，用户一保存就把这次进程的
    临时 `LOOKLIFT_*` 覆盖固化进 config.toml。要求表单可编辑字段
    （provider/model）取自 `load_config(include_env=False)` 的磁盘值；env
    只影响 `configured` 判定，不影响回显/保存的表单值。"""
    monkeypatch.setattr(api.shutil, "which", lambda _: None)
    _request(running_server, "POST", "/api/config", {"provider": "api", "model": "disk-model"})
    monkeypatch.setenv("LOOKLIFT_MODEL", "env-model")
    monkeypatch.setenv("LOOKLIFT_PROVIDER", "cli")

    status, data = _request(running_server, "GET", "/api/config")

    assert status == 200
    assert data["model"] == "disk-model"  # 回显磁盘值，不是 env 覆盖值
    assert data["provider"] == "api"


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


def test_post_config_does_not_bake_transient_env_override_into_saved_file(running_server, monkeypatch):
    """代码评审(Minor，env-baking):`_post_config` 拿 `load_config()` 当合并
    基准会连带 LOOKLIFT_* 环境变量的临时覆盖一起写进 config.toml——环境变量
    本该是"这次进程运行期间生效"，不该被一次保存动作意外固化成永久配置。
    这里设一个 `LOOKLIFT_LOOKS_DIR` 环境变量（POST 请求体完全不碰这个字段），
    保存后直接读磁盘文件内容，确认环境变量的值没有被写进去——`looks_dir`
    这个 key 本身依然会出现（`save_config` 对 `_DEFAULTS` 里的字段一视同仁，
    没配就写空字符串），断言点是"值不是环境变量那个"，不是"key 不存在"。
    """
    monkeypatch.setattr(api.shutil, "which", lambda _: None)
    monkeypatch.setenv("LOOKLIFT_LOOKS_DIR", "/env/should/not/be/saved")

    status, data = _request(running_server, "POST", "/api/config", {"provider": "cli"})

    assert status == 200
    saved_text = config.CONFIG_PATH.read_text(encoding="utf-8")
    assert "/env/should/not/be/saved" not in saved_text
    assert config.load_config(include_env=False)["looks_dir"] == ""


# ─── 纯函数:analyze 是否可用 ────────────────────────────────────────────


def test_analyze_would_work_true_when_provider_explicit():
    assert api._analyze_would_work({"provider": "cli", "api_key": "", "model": "", "base_url": ""}) is True
    assert api._analyze_would_work({"provider": "api", "api_key": "", "model": "", "base_url": ""}) is True


def test_analyze_would_work_true_when_api_key_present():
    assert api._analyze_would_work({"provider": "auto", "api_key": "sk-x", "model": "", "base_url": ""}) is True


def test_analyze_would_work_true_when_anthropic_api_key_env_present(monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda _: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-env")
    assert api._analyze_would_work({"provider": "auto", "api_key": "", "model": "", "base_url": ""}) is True


def test_analyze_would_work_false_when_nothing_available(monkeypatch):
    monkeypatch.setattr(api.shutil, "which", lambda _: None)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
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


def test_index_html_has_no_duplicate_ids():
    """代码评审(Important，wizard cloneNode 重复 id):静态标记本身不能有重复
    id——这条守住 index.html 这一份源头；运行时向导克隆 #settings-form 后
    还得再做一次 id 改写（见 app.js 的 `_dedupeClonedIds`），那部分不经浏览器
    没法直接单测，用下面 `test_app_js_wizard_clone_dedupes_cloned_ids` 从 JS
    源码字符串层面守住"克隆后确实调用了改写逻辑"这件事。
    """
    text = _index_html_text()
    ids = re.findall(r'\bid="([^"]+)"', text)
    duplicates = {i for i in ids if ids.count(i) > 1}
    assert not duplicates, f"index.html 出现重复 id：{duplicates}"


def test_app_js_wizard_clone_dedupes_cloned_ids():
    """向导表单是 `#settings-form` 的 `cloneNode(true)`，克隆前 DOM 里同时
    存在两份 `id="settings-model"`/`id="settings-api-key"`（原表单 + 克隆），
    首屏点标签会误聚焦到隐藏的设置面板输入框上。要求 `showWizard` 在插入
    克隆节点前调用一个 id 改写函数，把克隆内部的 id（以及配套的
    `label[for]`）全部换成不冲突的新值。"""
    text = (Path(__file__).parent.parent / "looklift" / "gui" / "static" / "js" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "_dedupeClonedIds" in text, "app.js 缺少克隆 id 改写函数 _dedupeClonedIds"

    show_wizard_start = text.index("function showWizard")
    show_wizard_body = text[show_wizard_start : show_wizard_start + 2000]
    assert "_dedupeClonedIds(clone" in show_wizard_body, "showWizard 必须在插入克隆节点前调用 _dedupeClonedIds"
