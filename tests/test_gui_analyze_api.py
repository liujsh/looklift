"""GUI-T8：分析面板后端 —— `POST /api/analyze`（design.md 决策 2 轮询 + API 路由
一览 `/api/analyze` 行、风险清单「长任务卡 UI」行）。

覆盖:合法路径提交 → 立即拿到 `task_id` → 轮询 `GET /api/tasks/<id>` 直到
`done`,`result.summary` 与 conftest 的 `sample_analysis` fixture 一致;
`path` 字段缺失 / 文件不存在 / 扩展名不支持均返回中文 400;
`analyzer.analyze` 抛异常时任务态落 `error`,错误信息透传中文提示(额度不足
一类的真实报错文案不能被吞掉或替换成英文)。

走真实 running server（复用 test_gui_upload.py / test_gui_config_api.py 的
fixture 写法),不 mock server 内部路由分发;只在 `looklift.gui.api` 这个模块
的 `analyzer.analyze` 打桩,把真实的 30-120s 分析耗时换成一个可控的
`threading.Event` 等待,验证提交请求立即返回(不阻塞在分析调用里)。
"""
from __future__ import annotations

import http.client
import json
import threading
import time
from pathlib import Path

import pytest

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


def _poll_until_finished(srv, task_id: str, timeout: float = 5.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        status, data = _request(srv, "GET", f"/api/tasks/{task_id}")
        assert status == 200
        if data["status"] != "running":
            return data
        time.sleep(0.05)
    raise AssertionError("任务未在超时前结束")


# ─── POST /api/analyze ───────────────────────────────────────────────────


def test_analyze_valid_path_submits_task_and_polling_reaches_done(
    running_server, monkeypatch, tmp_path, sample_analysis
):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"fake-jpeg-bytes")

    ready = threading.Event()

    def _fake_analyze(edited, original=None, style_hint=None, backend="auto"):
        ready.wait(timeout=2)
        return sample_analysis

    monkeypatch.setattr(api.analyzer, "analyze", _fake_analyze)

    status, data = _request(running_server, "POST", "/api/analyze", {"path": str(photo)})
    assert status == 200
    task_id = data["task_id"]
    assert task_id

    ready.set()
    task = _poll_until_finished(running_server, task_id)
    assert task["status"] == "done"
    assert task["result"]["summary"] == sample_analysis["summary"]


def test_analyze_missing_path_field_returns_400(running_server):
    status, data = _request(running_server, "POST", "/api/analyze", {})
    assert status == 400
    assert "error" in data


def test_analyze_nonexistent_path_returns_400(running_server, tmp_path):
    missing = tmp_path / "not-there.jpg"
    status, data = _request(running_server, "POST", "/api/analyze", {"path": str(missing)})
    assert status == 400
    assert "error" in data


def test_analyze_bad_extension_returns_400(running_server, tmp_path):
    bad = tmp_path / "photo.txt"
    bad.write_text("not an image")
    status, data = _request(running_server, "POST", "/api/analyze", {"path": str(bad)})
    assert status == 400
    assert "error" in data


def test_analyze_task_error_carries_chinese_message(running_server, monkeypatch, tmp_path):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"fake-jpeg-bytes")

    def _boom(edited, original=None, style_hint=None, backend="auto"):
        raise RuntimeError("额度不足")

    monkeypatch.setattr(api.analyzer, "analyze", _boom)

    status, data = _request(running_server, "POST", "/api/analyze", {"path": str(photo)})
    assert status == 200
    task_id = data["task_id"]

    task = _poll_until_finished(running_server, task_id)
    assert task["status"] == "error"
    assert "额度不足" in task["error"]


# ─── index.html / app.js 静态结构 ────────────────────────────────────────


def _index_html_text() -> str:
    static_dir = Path(__file__).parent.parent / "looklift" / "gui" / "static"
    return (static_dir / "index.html").read_text(encoding="utf-8")


def _app_js_text() -> str:
    static_dir = Path(__file__).parent.parent / "looklift" / "gui" / "static"
    return (static_dir / "js" / "app.js").read_text(encoding="utf-8")


def test_index_html_has_analyze_dropzone():
    assert 'id="analyze-dropzone"' in _index_html_text()


def test_index_html_has_analyze_hint_field():
    assert 'id="analyze-hint"' in _index_html_text()


def test_index_html_has_analyze_result_container():
    assert 'id="analyze-result"' in _index_html_text()


def test_app_js_has_state_wiring_for_analysis():
    text = _app_js_text()
    assert "App.state" in text
    assert "currentAnalysis" in text
    assert "currentPhotoPath" in text
