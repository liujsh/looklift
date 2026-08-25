"""Connector/MCP Source Packet 的不可信输入封装。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import re
from io import BytesIO
from typing import Any

from PIL import Image, UnidentifiedImageError

from .agent_adapter import AgentImage
from .proposal import Proposal, ProposalService


@dataclass(frozen=True)
class ConnectorManifest:
    connector_id: str
    protocol: str
    receiver: str
    capabilities: frozenset[str]

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", self.connector_id):
            raise ValueError("Connector ID 不安全")
        if self.protocol not in {"https", "mcp", "local"}:
            raise ValueError("Connector 协议不受支持")
        if not self.receiver:
            raise ValueError("Connector 必须声明数据接收方")


@dataclass(frozen=True)
class SourcePacket:
    packet_id: str
    source: str
    retrieved_at: str
    content_hash: str
    content: dict[str, Any]
    sensitivity: str = "normal"


class SourcePacketStore:
    def __init__(self) -> None:
        self._packets: dict[str, SourcePacket] = {}

    def put(self, packet: SourcePacket) -> SourcePacket:
        existing = self._packets.get(packet.packet_id)
        if existing is not None and existing.content_hash != packet.content_hash:
            raise ValueError("Source Packet ID 冲突")
        self._packets[packet.packet_id] = packet
        return packet

    def get(self, packet_id: str) -> SourcePacket:
        try:
            return self._packets[packet_id]
        except KeyError as exc:
            raise ValueError("Source Packet 不存在") from exc

    def propose(
        self,
        packet_id: str,
        *,
        service: ProposalService,
        target_type: str,
        target_id: str,
        base_hash: str,
        patch: dict[str, Any],
    ) -> Proposal:
        packet = self.get(packet_id)
        return service.preview(
            target_type=target_type,
            target_id=target_id,
            base_hash=base_hash,
            patch=patch,
            source_packet_ids=(packet.packet_id,),
        )


@dataclass(frozen=True)
class ProviderEnvelope:
    receiver: str
    image: AgentImage


class ProviderGateway:
    """外发前只接受无 EXIF、最长边不超过 2048 的 JPEG 代理图。"""

    def __init__(self, *, allowed_receivers: set[str]) -> None:
        self._allowed_receivers = frozenset(allowed_receivers)

    def prepare_proxy_image(self, *, receiver: str, content: bytes) -> ProviderEnvelope:
        if receiver not in self._allowed_receivers:
            raise ValueError("数据接收方未获授权")
        try:
            with Image.open(BytesIO(content)) as image:
                if image.format != "JPEG":
                    raise ValueError("Provider 代理图必须是 JPEG")
                if max(image.size) > 2048:
                    raise ValueError("Provider 代理图最长边不能超过 2048px")
                if image.getexif():
                    raise ValueError("Provider 代理图必须移除 EXIF")
                image.verify()
        except UnidentifiedImageError as exc:
            raise ValueError("Provider 代理图不是有效图片") from exc
        return ProviderEnvelope(receiver=receiver, image=AgentImage("image/jpeg", content))


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
