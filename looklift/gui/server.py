"""本地 HTTP server：`ThreadingHTTPServer` + 路由分发（静态资源 / `/api/*` / `/report/<name>`）。

只信任本机：绑定 `127.0.0.1`，不监听 `0.0.0.0` 或局域网可达的网卡。
"""
from __future__ import annotations

import json
import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

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

_CORS_ORIGINS = {
    "http://localhost:1420",
    "http://tauri.localhost",
    "https://tauri.localhost",
    "tauri://localhost",
}


def create_server(port: int = 0, token: str | None = None) -> ThreadingHTTPServer:
    """创建绑定 `127.0.0.1:<port>` 的 server。

    `token` 只供 Tauri sidecar 模式启用；旧 pywebview 入口与现有
    测试不传 token，保持原契约。
    """
    server = ThreadingHTTPServer(("127.0.0.1", port), _RequestHandler)
    server.looklift_token = token  # type: ignore[attr-defined]
    return server


class _RequestHandler(BaseHTTPRequestHandler):
    """路由分发：静态资源 `/` `/static/*` / `/api/*` 与 `/report/<name>` / 其余 404。"""

    def log_message(self, format: str, *args: object) -> None:
        pass  # 静默逐请求日志，保持测试输出干净

    def do_GET(self) -> None:
        self._dispatch("GET")

    def do_POST(self) -> None:
        self._dispatch("POST")

    def do_OPTIONS(self) -> None:
        """只为受信 Tauri/Vite origin 回应带自定义令牌头的预检。"""
        path = unquote(urlsplit(self.path).path)
        if path.startswith("/api/") and self._cors_origin() is not None:
            self.send_response(HTTPStatus.NO_CONTENT)
            self._send_cors_headers(preflight=True)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self._send_json(HTTPStatus.FORBIDDEN, {"error": "不允许的请求来源"})

    def _dispatch(self, method: str) -> None:
        path = unquote(urlsplit(self.path).path)
        try:
            if path.startswith("/api/") and not self._authorized():
                self._send_json(HTTPStatus.UNAUTHORIZED, {"error": "启动令牌无效"})
            elif method == "GET" and path == "/":
                self._serve_static("index.html")
            elif method == "GET" and path.startswith("/static/"):
                self._serve_static(path[len("/static/") :])
            elif path.startswith("/api/") or path.startswith("/report/"):
                self._dispatch_api(method, path)
            else:
                self._send_json(HTTPStatus.NOT_FOUND, {"error": f"未找到路径：{path}"})
        except Exception as exc:  # noqa: BLE001 —— handler 异常一律转 500 JSON，不吐 traceback
            self._send_json(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": str(exc)})

    def _authorized(self) -> bool:
        """校验 Tauri 启动时生成的本机令牌；未配置时保持旧行为。"""
        expected = getattr(self.server, "looklift_token", None)
        if expected is None:
            return True
        actual = self.headers.get("X-Looklift-Token", "")
        return hmac.compare_digest(actual, expected)

    def _cors_origin(self) -> str | None:
        origin = self.headers.get("Origin")
        return origin if origin in _CORS_ORIGINS else None

    def _send_cors_headers(self, *, preflight: bool = False) -> None:
        origin = self._cors_origin()
        if origin is None:
            return
        self.send_header("Access-Control-Allow-Origin", origin)
        self.send_header("Vary", "Origin")
        if preflight:
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Looklift-Token")
            self.send_header("Access-Control-Max-Age", "600")

    def _dispatch_api(self, method: str, path: str) -> None:
        matched = _match_route(method, path)
        if matched is None:
            self._send_json(HTTPStatus.NOT_FOUND, {"error": f"未找到路径：{path}"})
            return
        handler, params = matched
        context = {
            "params": params,
            "body": self._read_body(),
            "content_type": self.headers.get("Content-Type", ""),
            "query": {key: values[0] for key, values in parse_qs(urlsplit(self.path).query).items()},
        }
        result = handler(context)
        # 一条干净的分发分支:handler 返回三元组即二进制响应（如
        # `/api/preview` 的 JPEG 字节），两元组沿用原有 JSON 响应，不为此
        # 拆两套 Handler 签名或额外的 content-type 协商机制。
        if len(result) == 3:
            status, data, content_type = result
            self._send_binary(status, data, content_type)
        else:
            status, body = result
            self._send_json(status, body)

    def _read_body(self) -> bytes | None:
        """按 `Content-Length` 读取请求体；没有该头（如大多数 GET 请求）时返回
        `None`，与「有一个空 body」区分开。"""
        length_header = self.headers.get("Content-Length")
        if length_header is None:
            return None
        try:
            length = int(length_header)
        except ValueError:
            return None
        if length <= 0:
            return None
        return self.rfile.read(length)

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

    def _send_binary(self, status: int, data: bytes, content_type: str) -> None:
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, status: int, body: dict) -> None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
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
