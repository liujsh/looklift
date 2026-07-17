"""供应商共用的标准库 JSON HTTP 传输。"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class HTTPStatusError(RuntimeError):
    """HTTP 服务返回非成功状态。"""

    def __init__(self, status: int, body: str):
        self.status = status
        self.body = body
        super().__init__(f"HTTP {status}: {body}")


class HTTPConnectionError(RuntimeError):
    """请求在取得 HTTP 响应前失败。"""


def post_json(
    url: str,
    payload: dict[str, Any],
    *,
    headers: dict[str, str] | None = None,
    timeout: int,
    opener: Callable[..., Any] = urlopen,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any]:
    """POST JSON；连接错误与 5xx 重试一次，4xx 立即失败。"""
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    request = Request(
        url,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=request_headers,
        method="POST",
    )

    for attempt in range(2):
        try:
            with opener(request, timeout=timeout) as response:
                body = response.read().decode("utf-8")
            try:
                decoded = json.loads(body)
            except json.JSONDecodeError:
                raise RuntimeError("供应商返回了无法解析的 JSON 响应。") from None
            if not isinstance(decoded, dict):
                raise RuntimeError("供应商返回的 JSON 顶层必须是对象。")
            return decoded
        except HTTPError as exc:
            body = _read_error_body(exc)
            if exc.code >= 500 and attempt == 0:
                sleeper(0.25)
                continue
            raise HTTPStatusError(exc.code, body) from None
        except (URLError, TimeoutError, OSError) as exc:
            if attempt == 0:
                sleeper(0.25)
                continue
            reason = getattr(exc, "reason", exc)
            raise HTTPConnectionError(str(reason)) from None

    raise AssertionError("重试循环不应到达这里")


def _read_error_body(exc: HTTPError) -> str:
    """尽力读取错误响应，读取失败时保留 HTTP 原因。"""
    try:
        return exc.read().decode("utf-8", errors="replace")
    except Exception:
        return str(exc.reason)
