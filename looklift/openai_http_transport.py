"""受控的 OpenAI-compatible HTTP 流传输。"""

from __future__ import annotations

import asyncio
import socket
from collections.abc import AsyncIterator, Callable
from urllib.parse import urlparse

import httpx

from .provider_security import ProviderSecurityError, validate_provider_url
from .provider_snapshot import ProviderProtocol, ProviderSnapshot


class OpenAiTransportError(RuntimeError):
    """已分类且不携带 Provider 原始响应的传输错误。"""


AddressResolver = Callable[[str], tuple[str, ...]]


def _resolve(hostname: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                item[4][0]
                for item in socket.getaddrinfo(
                    hostname, None, type=socket.SOCK_STREAM
                )
            }
        )
    )


class HttpxOpenAiTransport:
    def __init__(
        self,
        *,
        resolver: AddressResolver = _resolve,
        timeout_seconds: float = 120,
        response_limit_bytes: int = 8 * 1024 * 1024,
    ) -> None:
        self._resolver = resolver
        self._timeout = timeout_seconds
        self._limit = response_limit_bytes

    async def stream(
        self,
        snapshot: ProviderSnapshot,
        request: dict,
        *,
        api_key: str | None,
    ) -> AsyncIterator[bytes]:
        parsed = urlparse(snapshot.base_url)
        assert parsed.hostname is not None
        resolved = await asyncio.to_thread(self._resolver, parsed.hostname)
        local_ollama = (
            snapshot.protocol is ProviderProtocol.OLLAMA_OPENAI_COMPATIBLE
        )
        validate_provider_url(
            snapshot.base_url,
            resolved_ips=resolved,
            local_ollama=local_ollama,
        )
        url = f"{snapshot.base_url.rstrip('/')}/chat/completions"
        headers = {"Accept": "text/event-stream"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        total = 0
        try:
            async with httpx.AsyncClient(
                follow_redirects=False,
                trust_env=False,
                timeout=self._timeout,
            ) as client:
                async with client.stream(
                    "POST", url, headers=headers, json=request
                ) as response:
                    if response.is_redirect:
                        raise ProviderSecurityError("Provider 不允许重定向")
                    if response.status_code == 401:
                        raise OpenAiTransportError("Provider 认证失败")
                    if response.status_code == 429:
                        raise OpenAiTransportError("Provider 请求受到限流")
                    if response.status_code >= 400:
                        raise OpenAiTransportError("Provider 请求失败")
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > self._limit:
                            raise ProviderSecurityError("Provider 响应超过大小限制")
                        yield chunk
        except (ProviderSecurityError, OpenAiTransportError):
            raise
        except (httpx.HTTPError, OSError) as exc:
            raise OpenAiTransportError("Provider 连接失败") from exc
