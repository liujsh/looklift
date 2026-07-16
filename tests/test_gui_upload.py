"""GUI-T6：`POST /api/upload` 测试（design.md 决策 4 里 browser 模式落临时文件的那一半）。

手写 multipart/form-data 请求体（不依赖 requests 之类的第三方库），走真实
running server，覆盖：happy path 落盘、无文件字段、请求体损坏、超过大小上限、
文件名清洗（Windows 保留字符集/控制字符/路径分隔符/首尾点空格全部处理掉，
清洗后仍然写盘失败时不泄漏本地文件系统路径）。

纯字符串处理的 `upload.sanitize_filename` 额外有不经 HTTP 的直接单测，跑得更快、
边界情况更好穷举。
"""
from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path

import pytest

from looklift.gui import server as gui_server
from looklift.gui import upload


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
    生成带 filename 的文件字段（filename 里的 `\\`/`"` 按 RFC 2183 转义，和真实
    浏览器行为一致，这样才能在请求体里塞含双引号的恶意文件名做测试）；否则当
    作普通文本字段。
    """
    parts = []
    for name, value in fields.items():
        if isinstance(value, tuple):
            filename, content, content_type = value
            escaped_filename = filename.replace("\\", "\\\\").replace('"', '\\"')
            head = (
                f'--{boundary}\r\n'
                f'Content-Disposition: form-data; name="{name}"; filename="{escaped_filename}"\r\n'
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
    monkeypatch.setattr(upload, "MAX_UPLOAD_BYTES", 1024)
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


# ─── 代码评审复现用例：Windows 保留字符集 ──────────────────────────────
#
# 复现的问题：旧版 `_sanitize_filename` 只处理了 `/`、`\`，对 Windows 保留字符
# 集 `< > : " | ? *` 毫无防备——`a"b.jpg` 被静默截断保存、`a:b.jpg` 在 NTFS 上
# 会被解释成"文件名:备用数据流名"、`a<b>.jpg`/`a|b.jpg` 直接触发未捕获的
# OSError 变成 500（响应体还带着本机用户名在内的完整临时文件路径）。
# 这里挨个用真实请求复现，断言全部落在「200 且文件名已清洗」或「400 通用中文
# 提示」这两条路径上，绝不允许 500，也不允许错误信息里出现盘符/反斜杠路径。


@pytest.mark.parametrize(
    "raw_filename",
    ['a"b.jpg', "a:b.jpg", "a<b>.jpg", "a|b.jpg", "a?b.jpg", "a*b.jpg"],
)
def test_upload_sanitizes_windows_reserved_characters_never_500s(running_server, raw_filename):
    content_type, body = _build_multipart({"file": (raw_filename, b"payload-bytes", "image/jpeg")})

    status, _, resp_body = _post(running_server, "/api/upload", body, content_type)

    assert status == 200, f"文件名 {raw_filename!r} 触发了 {status}，响应体：{resp_body!r}"
    data = json.loads(resp_body)
    saved = Path(data["path"])
    assert saved.is_file()
    assert saved.read_bytes() == b"payload-bytes"
    for reserved in '<>:"|?*':
        assert reserved not in saved.name, f"清洗后的文件名仍带保留字符 {reserved!r}：{saved.name}"


def test_upload_write_failure_returns_400_without_leaking_filesystem_path(running_server, monkeypatch):
    """即便清洗兜不住（比如未来又冒出一个没考虑到的非法字符组合），落盘这一步
    自己也要有 try/except 兜底：转成通用中文 400，绝不把 `str(exc)`（往往带着
    完整本地路径、用户名）原样回显给客户端。"""
    leaking_path = 'C:\\Users\\someone\\AppData\\Local\\Temp\\looklift-upload-abc123\\x_a.jpg'

    def _boom(dest_dir, filename, content):
        raise OSError(f"[WinError 123] 文件名、目录名或卷标语法不正确: '{leaking_path}'")

    monkeypatch.setattr(upload, "save_upload", _boom)

    content_type, body = _build_multipart({"file": ("a.jpg", b"data", "image/jpeg")})
    status, _, resp_body = _post(running_server, "/api/upload", body, content_type)

    assert status == 400
    text = resp_body.decode("utf-8")
    assert "error" in json.loads(resp_body)
    assert "C:\\" not in text
    assert "someone" not in text
    assert "文件名不合法" in text


# ─── upload.sanitize_filename 纯函数单测（不经 HTTP，边界情况穷举更快）───


@pytest.mark.parametrize("reserved", list('<>:"|?*'))
def test_sanitize_filename_replaces_each_reserved_character(reserved):
    result = upload.sanitize_filename(f"a{reserved}b.jpg")
    assert reserved not in result
    assert result.endswith(".jpg")


def test_sanitize_filename_strips_control_chars_and_nul():
    result = upload.sanitize_filename("a\x00b\x01c\x1fd.jpg")
    assert "\x00" not in result
    assert "\x01" not in result
    assert "\x1f" not in result


def test_sanitize_filename_strips_leading_trailing_dots_and_spaces():
    assert upload.sanitize_filename("  ..hidden.jpg..  ") == "hidden.jpg"


def test_sanitize_filename_empty_after_cleanup_falls_back_to_upload_bin():
    assert upload.sanitize_filename("...") == "upload.bin"
    assert upload.sanitize_filename("   ") == "upload.bin"
    assert upload.sanitize_filename("") == "upload.bin"


def test_sanitize_filename_strips_path_separators_both_slash_styles():
    assert upload.sanitize_filename("../../etc/passwd.jpg") == "passwd.jpg"
    assert upload.sanitize_filename("C:\\Users\\me\\a.jpg") == "a.jpg"
