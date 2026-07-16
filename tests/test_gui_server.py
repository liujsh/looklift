"""server.py + tasks.py 集成测试：真实起 server（端口 0），用 http.client 打请求。"""
from __future__ import annotations

import http.client
import json
import threading

import pytest

from looklift.gui import server as gui_server
from looklift.gui import tasks


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


def _get(srv, path):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        body = resp.read()
        return resp.status, resp.getheader("Content-Type"), body
    finally:
        conn.close()


def _poll_until_finished(srv, task_id):
    """轮询任务直到不再是 running；不用 sleep，靠 HTTP 往返自身的调度间隙。"""
    data = None
    for _ in range(500):
        _, _, body = _get(srv, f"/api/tasks/{task_id}")
        data = json.loads(body)
        if data["status"] != "running":
            return data
    return data


def test_root_serves_index_html(running_server):
    status, content_type, body = _get(running_server, "/")
    assert status == 200
    assert "text/html" in content_type
    assert b"looklift" in body


def test_unknown_path_returns_404_json(running_server):
    status, content_type, body = _get(running_server, "/nonexistent")
    assert status == 404
    assert "application/json" in content_type
    assert "error" in json.loads(body)


@pytest.mark.parametrize(
    "path",
    [
        "/static/../../pyproject.toml",
        "/static/..%2f..%2fpyproject.toml",
        "/static/%2e%2e/%2e%2e/pyproject.toml",
    ],
)
def test_static_path_traversal_rejected(running_server, path):
    status, content_type, body = _get(running_server, path)
    assert status == 404
    assert "application/json" in content_type
    assert "error" in json.loads(body)


def test_static_serves_existing_asset(running_server):
    status, content_type, body = _get(running_server, "/static/vendor/claude/tokens.css")
    assert status == 200
    assert "text/css" in content_type
    assert len(body) > 0


def test_api_ping(running_server):
    status, content_type, body = _get(running_server, "/api/ping")
    assert status == 200
    assert "application/json" in content_type
    assert json.loads(body) == {"ok": True}


def test_report_placeholder_is_501(running_server):
    status, _, body = _get(running_server, "/report/some-look")
    assert status == 501
    assert "error" in json.loads(body)


def test_tasks_unknown_id_returns_404(running_server):
    status, _, body = _get(running_server, "/api/tasks/does-not-exist")
    assert status == 404
    assert "error" in json.loads(body)


def test_tasks_running_then_done_with_result(running_server):
    gate = threading.Event()

    def slow():
        gate.wait(timeout=5)
        return {"value": 42}

    task_id = tasks.submit(slow)

    _, _, body = _get(running_server, f"/api/tasks/{task_id}")
    assert json.loads(body)["status"] == "running"

    gate.set()
    data = _poll_until_finished(running_server, task_id)
    assert data["status"] == "done"
    assert data["result"] == {"value": 42}
    assert data["error"] is None


def test_tasks_error_state_carries_chinese_message(running_server):
    def boom():
        raise ValueError("坏了：参数不对")

    task_id = tasks.submit(boom)

    data = _poll_until_finished(running_server, task_id)
    assert data["status"] == "error"
    assert data["result"] is None
    assert "坏了：参数不对" in data["error"]
