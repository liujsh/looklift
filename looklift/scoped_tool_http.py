"""Pi 只读扩展到 Scoped Tool Gateway 的 localhost HTTP 传输。"""

from __future__ import annotations

import base64
import json
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from .scoped_tool_gateway import GatewayToolResult, ScopedToolGateway


_MAX_REQUEST_BYTES = 256 * 1024
_AUTHORIZATION_ERRORS = frozenset(
    {"token_invalid", "token_revoked", "token_expired"}
)


class _LocalThreadingServer(ThreadingHTTPServer):
    daemon_threads = True


class ScopedToolHttpServer:
    """只监听 127.0.0.1 随机端口，不记录请求、Token 或图片。"""

    def __init__(self, gateway: ScopedToolGateway) -> None:
        self._gateway = gateway
        self._server: _LocalThreadingServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("Tool Gateway HTTP Server 尚未启动")
        return f"http://127.0.0.1:{self._server.server_port}"

    def start(self) -> None:
        if self._server is not None:
            raise RuntimeError("Tool Gateway HTTP Server 不能重复启动")
        gateway = self._gateway

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                _handle_post(self, gateway)

            def log_message(self, _format: str, *args: Any) -> None:
                return

        self._server = _LocalThreadingServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            daemon=True,
            name="looklift-scoped-tools",
        )
        self._thread.start()

    def close(self) -> None:
        server = self._server
        thread = self._thread
        self._server = None
        self._thread = None
        if server is None:
            return
        server.shutdown()
        server.server_close()
        if thread is not None:
            thread.join(timeout=1)


def _handle_post(
    handler: BaseHTTPRequestHandler,
    gateway: ScopedToolGateway,
) -> None:
    prefix = "/tools/"
    if not handler.path.startswith(prefix) or "/" in handler.path[len(prefix) :]:
        _send_json(handler, HTTPStatus.NOT_FOUND, {"error": "not_found"})
        return
    length = _content_length(handler)
    if length is None:
        _send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
        return
    try:
        value = json.loads(handler.rfile.read(length))
    except (UnicodeDecodeError, json.JSONDecodeError):
        _send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
        return
    if not isinstance(value, dict):
        _send_json(handler, HTTPStatus.BAD_REQUEST, {"error": "invalid_request"})
        return
    authorization = handler.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        _send_json(handler, HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
        return
    token = authorization.removeprefix("Bearer ")
    tool_name = handler.path[len(prefix) :]
    result = gateway.call(token, tool_name, value)
    if _authorization_failed(result):
        _send_json(handler, HTTPStatus.UNAUTHORIZED, {"error": "unauthorized"})
        return
    response: dict[str, Any] = {"result": dict(result.payload)}
    if result.preview_jpeg is not None:
        response["preview_base64"] = base64.b64encode(result.preview_jpeg).decode("ascii")
    _send_json(handler, HTTPStatus.OK, response)


def _content_length(handler: BaseHTTPRequestHandler) -> int | None:
    if handler.headers.get_content_type() != "application/json":
        return None
    try:
        length = int(handler.headers.get("Content-Length", ""))
    except ValueError:
        return None
    return length if 0 < length <= _MAX_REQUEST_BYTES else None


def _authorization_failed(result: GatewayToolResult) -> bool:
    error = result.payload.get("error")
    return isinstance(error, dict) and error.get("code") in _AUTHORIZATION_ERRORS


def _send_json(
    handler: BaseHTTPRequestHandler,
    status: HTTPStatus,
    payload: dict[str, Any],
) -> None:
    content = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    handler.send_response(status.value)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(content)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    try:
        handler.wfile.write(content)
    except (BrokenPipeError, ConnectionResetError):
        return
