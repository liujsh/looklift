"""server.py + tasks.py 集成测试：真实起 server（端口 0），用 http.client 打请求。"""
from __future__ import annotations

import http.client
import json
import re
import threading
from pathlib import Path

import pytest

from looklift.gui import server as gui_server
from looklift.gui import tasks

_HTML_HREF_SRC_RE = re.compile(r'(?:href|src)\s*=\s*["\']([^"\']+)["\']')


def _index_html_local_refs() -> list[str]:
    """从 index.html 提取本地 href/src 引用（跳过绝对 URL），供下面的参数化测试用。"""
    index_path = Path(__file__).parent.parent / "looklift" / "gui" / "static" / "index.html"
    text = index_path.read_text(encoding="utf-8")
    return [ref for ref in _HTML_HREF_SRC_RE.findall(text) if not ref.startswith(("http://", "https://", "//"))]


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


def test_root_response_contains_panel_ids(running_server):
    """GUI-T5 冒烟：GET / 返回 200，且 body 里三个面板容器 id 都在。"""
    status, _, body = _get(running_server, "/")
    assert status == 200
    text = body.decode("utf-8")
    assert 'id="panel-analyze"' in text
    assert 'id="panel-looks"' in text
    assert 'id="panel-settings"' in text


@pytest.mark.parametrize("path", _index_html_local_refs())
def test_index_html_static_asset_paths_resolve_via_server(running_server, path):
    """index.html 引用的每个本地资源都必须以 /static/ 开头（server.py 只认
    "/"、"/static/*"、"/api/*"、"/report/* 四类前缀，裸相对路径会 404——这条
    断言本身是防止 index.html 退回不带前缀写法的回归门），且真的能通过运行中
    的 server 拿到 200。
    """
    assert path.startswith("/static/"), f"index.html 的本地引用必须以 /static/ 开头：{path}"
    status, content_type, body = _get(running_server, path)
    assert status == 200
    assert len(body) > 0


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


def test_task_dict_carries_message_key(running_server):
    """决策 2 的任务态形状是 `{status, message, result, error}`；`message` 在
    运行中应为「运行中」，结束（done/error）后 None 也是合法值。"""
    gate = threading.Event()
    task_id = tasks.submit(lambda: gate.wait(timeout=5) or {"ok": True})

    _, _, running_body = _get(running_server, f"/api/tasks/{task_id}")
    running_data = json.loads(running_body)
    assert "message" in running_data
    assert running_data["message"] == "运行中"

    gate.set()
    done_data = _poll_until_finished(running_server, task_id)
    assert "message" in done_data


def test_route_handler_exception_returns_500_json(running_server, monkeypatch):
    """500 兜底路径：临时注册一个必炸的路由，确认 `_dispatch` 的兜底 except
    把异常转成 500 JSON `{"error"}`，而不是让 traceback 泄漏给客户端。"""
    from looklift.gui import api

    def _boom(ctx):
        raise RuntimeError("路由 handler 内部炸了")

    original_routes = dict(api.ROUTES)
    api.ROUTES[("GET", "/api/__boom__")] = _boom
    try:
        status, content_type, body = _get(running_server, "/api/__boom__")
        assert status == 500
        assert "application/json" in content_type
        data = json.loads(body)
        assert "error" in data
        assert "路由 handler 内部炸了" in data["error"]
    finally:
        api.ROUTES.clear()
        api.ROUTES.update(original_routes)
