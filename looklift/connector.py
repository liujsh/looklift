"""Connector/MCP Source Packet 的不可信输入封装。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from typing import Any


@dataclass(frozen=True)
class SourcePacket:
    packet_id: str
    source: str
    retrieved_at: str
    content_hash: str
    content: dict[str, Any]
    sensitivity: str = "normal"


def make_source_packet(packet_id: str, source: str, content: dict[str, Any], *, sensitivity: str = "normal") -> SourcePacket:
    encoded = json.dumps(content, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return SourcePacket(packet_id, source, datetime.now(timezone.utc).isoformat(), hashlib.sha256(encoded.encode()).hexdigest(), dict(content), sensitivity)


def validate_external_url(url: str, *, resolved_ips: tuple[str, ...]) -> None:
    """只校验已解析地址；网络请求由上层 Gateway 执行。"""
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in {"https"} or not parsed.hostname or not resolved_ips:
        raise ValueError("Connector 仅允许带解析结果的 HTTPS 地址")
    import ipaddress
    for value in resolved_ips:
        address = ipaddress.ip_address(value)
        if address.is_private or address.is_loopback or address.is_link_local or address.is_reserved:
            raise ValueError("Connector 地址落入禁止网络范围")
