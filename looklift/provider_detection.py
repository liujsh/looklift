"""用户显式触发的 Provider 连通性与模型探测。"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx

from .provider_security import ensure_response_size, validate_provider_url
from .provider_snapshot import ProviderProtocol, ProviderSnapshot


@dataclass(frozen=True)
class ProviderDetectionResult:
    available: bool
    models: tuple[str, ...] = ()
    error_code: str | None = None


def _resolve(hostname: str) -> tuple[str, ...]:
    return tuple(
        sorted({item[4][0] for item in socket.getaddrinfo(hostname, None)})
    )


def detect_provider(
    snapshot: ProviderSnapshot,
    *,
    api_key: str | None,
    resolver=_resolve,
    transport: httpx.BaseTransport | None = None,
) -> ProviderDetectionResult:
    try:
        hostname = urlparse(snapshot.base_url).hostname
        if hostname is None:
            raise ValueError
        validate_provider_url(
            snapshot.base_url,
            resolved_ips=resolver(hostname),
            local_ollama=(
                snapshot.protocol is ProviderProtocol.OLLAMA_OPENAI_COMPATIBLE
            ),
        )
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        with httpx.Client(
            transport=transport,
            trust_env=False,
            follow_redirects=False,
            timeout=10,
        ) as client:
            response = client.get(
                f"{snapshot.base_url.rstrip('/')}/models", headers=headers
            )
        if response.is_redirect:
            return ProviderDetectionResult(False, error_code="redirect_rejected")
        if response.status_code == 401:
            return ProviderDetectionResult(False, error_code="authentication_failed")
        if response.status_code >= 400:
            return ProviderDetectionResult(False, error_code="provider_failed")
        ensure_response_size(response.content, limit_bytes=1024 * 1024)
        data = response.json().get("data", [])
        models = tuple(
            item["id"]
            for item in data
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        )
        return ProviderDetectionResult(True, models=models)
    except Exception:
        return ProviderDetectionResult(False, error_code="connection_failed")
