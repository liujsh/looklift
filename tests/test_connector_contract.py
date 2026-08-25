from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image

from looklift.connector import (
    ConnectorManifest,
    ProviderGateway,
    SourcePacketStore,
    make_source_packet,
)
from looklift.proposal import ProposalService


def _jpeg(size=(32, 24), *, exif=False) -> bytes:
    output = BytesIO()
    image = Image.new("RGB", size, (128, 128, 128))
    metadata = Image.Exif()
    if exif:
        metadata[0x010F] = "secret-camera"
    image.save(output, format="JPEG", exif=metadata)
    return output.getvalue()


def test_connector_manifest_and_source_packet_store_are_stable():
    manifest = ConnectorManifest(
        connector_id="catalog",
        protocol="https",
        receiver="catalog.example",
        capabilities=frozenset({"connector.read_catalog"}),
    )
    assert manifest.receiver == "catalog.example"
    store = SourcePacketStore()
    packet = make_source_packet("packet", "catalog", {"look": "neutral"})
    store.put(packet)
    assert store.get("packet").content_hash == packet.content_hash
    assert store.put(packet) == packet


def test_source_packet_creates_shared_proposal_with_provenance():
    service = ProposalService()
    store = SourcePacketStore()
    packet = store.put(make_source_packet("p1", "catalog", {"preference": "neutral"}))
    proposal = store.propose(
        packet.packet_id,
        service=service,
        target_type="ProjectContext",
        target_id="project-a",
        base_hash="base",
        patch={"preference": "neutral"},
    )
    assert proposal.source_packet_ids == ("p1",)
    assert proposal.status == "preview"


def test_provider_gateway_accepts_only_small_exif_free_jpeg():
    gateway = ProviderGateway(allowed_receivers={"api.example"})
    envelope = gateway.prepare_proxy_image(
        receiver="api.example",
        content=_jpeg(),
    )
    assert envelope.image.media_type == "image/jpeg"
    assert envelope.receiver == "api.example"
    with pytest.raises(ValueError, match="EXIF"):
        gateway.prepare_proxy_image(receiver="api.example", content=_jpeg(exif=True))
    with pytest.raises(ValueError, match="2048"):
        gateway.prepare_proxy_image(receiver="api.example", content=_jpeg((2049, 16)))
    with pytest.raises(ValueError, match="接收方"):
        gateway.prepare_proxy_image(receiver="other.example", content=_jpeg())
