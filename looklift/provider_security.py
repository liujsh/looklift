"""Provider 地址与响应边界的集中安全校验。"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse


class ProviderSecurityError(ValueError):
    """Provider 配置越过网络安全边界。"""


_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def validate_provider_url(
    url: str,
    *,
    resolved_ips: tuple[str, ...],
    local_ollama: bool = False,
) -> None:
    """校验调用前最终解析结果，防止配置与 DNS 解析绕过。"""
    parsed = urlparse(url)
    if not parsed.hostname or parsed.username or parsed.password or not resolved_ips:
        raise ProviderSecurityError("Provider 地址无效")
    addresses = tuple(ipaddress.ip_address(value) for value in resolved_ips)
    if local_ollama:
        if parsed.scheme not in {"http", "https"} or not all(
            address.is_loopback for address in addresses
        ):
            raise ProviderSecurityError("本地 Ollama 只允许 loopback 地址")
        return
    if parsed.scheme != "https":
        raise ProviderSecurityError("远程 Provider 只允许 HTTPS")
    for address in addresses:
        if (
            address.is_private
            or address.is_loopback
            or address.is_link_local
            or address.is_reserved
            or address in _CGNAT
        ):
            raise ProviderSecurityError("Provider 地址落入禁止网络范围")


def ensure_response_size(content: bytes, *, limit_bytes: int) -> bytes:
    if limit_bytes < 1 or len(content) > limit_bytes:
        raise ProviderSecurityError("Provider 响应超过大小限制")
    return content
