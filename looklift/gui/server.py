"""本地 HTTP server：`ThreadingHTTPServer` + 路由分发（静态资源 / `/api/*` / `/report/<name>`）。

只信任本机：绑定 `127.0.0.1`，不监听 `0.0.0.0` 或局域网可达的网卡。
"""
from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from . import api

STATIC_DIR = (Path(__file__).parent / "static").resolve()

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
}


def create_server(port: int = 0) -> ThreadingHTTPServer:
    """创建绑定 `127.0.0.1:<port>` 的 server；`port=0` 时由 OS 分配空闲端口。"""
    return ThreadingHTTPServer(("127.0.0.1", port), _RequestHandler)


class _RequestHandler(BaseHTTPRequestHandler):
    """路由分发：静态资源 `/` `/static/*` / `/api/*` 与 `/report/<name>` / 其余 404。"""

    def log_message(self, format: str, *args: object) -> None:
        pass  # 静默逐请求日志，保持测试输出干净

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def _dispatch(self, method: str) -> None:
        path = unquote(urlsplit(self.path).path)
        try:
            if method == "GET" and path == "/":
                self._serve_static("index.html")
            elif method == "GET" and path.startswith("/static/"):
                self._serve_static(path[len("/static/") :])
            elif path.startswith("/api/") or path.startswith("/report/"):
                self._dispatch_api(method, path)
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": f"未找到路径：{path}"})
        except Exception as exc:  # noqa: BLE001 —— handler 异常一律转 500 JSON，不吐 traceback
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def _dispatch_api(self, method: str, path: str) -> None:
        matched = _match_route(method, path)
        if matched is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": f"未找到路径：{path}"})
            return
        handler, params = matched
        status, body = handler(params)
        self._send_json(status, body)

    def _serve_static(self, rel_path: str) -> None:
        resolved = (STATIC_DIR / rel_path).resolve()
        inside_static = resolved == STATIC_DIR or STATIC_DIR in resolved.parents
        if not inside_static or not resolved.is_file():
            self._send_json(HTTPStatus.NOT_FOUND, {"error": f"未找到路径：{rel_path}"})
            return
        content_type = _CONTENT_TYPES.get(resolved.suffix.lower(), "application/octet-stream")
        data = resolved.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _match_route(method: str, path: str) -> tuple[api.Handler, dict[str, str]] | None:
    """在 `api.ROUTES` 里找 `(method, pattern)` 匹配项，返回 handler + 捕获到的段参数。"""
    for (route_method, pattern), handler in api.ROUTES.items():
        if route_method != method:
            continue
        params = _match_pattern(pattern, path)
        if params is not None:
            return handler, params
    return None


def _match_pattern(pattern: str, path: str) -> dict[str, str] | None:
    """按 `/` 分段比较；`<name>` 段捕获为参数，其余段必须字面相等。"""
    pattern_segs = pattern.strip("/").split("/")
    path_segs = path.strip("/").split("/")
    if len(pattern_segs) != len(path_segs):
        return None
    params: dict[str, str] = {}
    for p_seg, seg in zip(pattern_segs, path_segs):
        if p_seg.startswith("<") and p_seg.endswith(">"):
            params[p_seg[1:-1]] = seg
        elif p_seg != seg:
            return None
    return params
