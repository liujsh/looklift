"""GUI-T6：`POST /api/upload` 测试（design.md 决策 4 里 browser 模式落临时文件的那一半）。

手写 multipart/form-data 请求体（不依赖 requests 之类的第三方库），走真实
running server，覆盖：happy path 落盘、无文件字段、请求体损坏、超过大小上限、
文件名清洗（去掉路径分隔符，防止穿越到上传目录之外）。
"""
from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path

import pytest

from looklift.gui import api
from looklift.gui import server as gui_server


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


def _build_multipart(fields: dict, boundary: str = "----looklifttestboundary") -> tuple[str, bytes]:
    """手写拼一份 multipart/form-data 请求体。

    `fields` 的 value 若是 `(filename, content_bytes, content_type)` 三元组则
    生成带 filename 的文件字段；否则当作普通文本字段。
    """
    parts = []
    for name, value in fields.items():
        if isinstance(value, tuple):
            filename, content, content_type = value
            head = (
                f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
                f'Content-Type: {content_type}\r\n\r\n'
            ).encode("utf-8")
            parts.append(head + content + b"\r\n")
        else:
            head = (
                f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f'{value}\r\n'
            ).encode("utf-8")
            parts.append(head)
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    body = b"".join(parts)
    content_type = f"multipart/form-data; boundary={boundary}"
    return content_type, body


def _post(srv, path: str, body: bytes, content_type: str):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
    try:
        conn.request(
            "POST",
            path,
            body=body,
            headers={"Content-Type": content_type, "Content-Length": str(len(body))},
        )
        resp = conn.getresponse()
        data = resp.read()
        return resp.status, resp.getheader("Content-Type"), data
    finally:
        conn.close()


def test_upload_happy_path_saves_file_and_returns_readable_path(running_server):
    content_type, body = _build_multipart({"file": ("photo.jpg", b"fake-jpeg-bytes", "image/jpeg")})
    status, resp_ct, resp_body = _post(running_server, "/api/upload", body, content_type)

    assert status == 200
    assert "application/json" in resp_ct
    data = json.loads(resp_body)
    saved = Path(data["path"])
    assert saved.is_file()
    assert saved.read_bytes() == b"fake-jpeg-bytes"


def test_upload_no_file_field_returns_400(running_server):
    content_type, body = _build_multipart({"note": "hello"})
    status, _, resp_body = _post(running_server, "/api/upload", body, content_type)

    assert status == 400
    assert "error" in json.loads(resp_body)


def test_upload_malformed_body_returns_400(running_server):
    status, _, resp_body = _post(
        running_server, "/api/upload", b"this is not a multipart body at all", "multipart/form-data; boundary=xxx"
    )

    assert status == 400
    assert "error" in json.loads(resp_body)


def test_upload_wrong_content_type_returns_400(running_server):
    status, _, resp_body = _post(running_server, "/api/upload", b"{}", "application/json")

    assert status == 400
    assert "error" in json.loads(resp_body)


def test_upload_over_size_cap_returns_413(running_server, monkeypatch):
    monkeypatch.setattr(api, "_MAX_UPLOAD_BYTES", 1024)
    content_type, body = _build_multipart({"file": ("big.jpg", b"x" * 2048, "image/jpeg")})

    status, resp_ct, resp_body = _post(running_server, "/api/upload", body, content_type)

    assert status == 413
    assert "application/json" in resp_ct
    assert "error" in json.loads(resp_body)


def test_upload_filename_sanitized_strips_path_separators(running_server):
    content_type, body = _build_multipart({"file": ("../../etc/passwd.jpg", b"data", "image/jpeg")})

    status, _, resp_body = _post(running_server, "/api/upload", body, content_type)

    assert status == 200
    saved = Path(json.loads(resp_body)["path"])
    assert saved.is_file()
    assert "/" not in saved.name
    assert "\\" not in saved.name
    assert ".." not in saved.name
    assert saved.name.endswith("passwd.jpg")
