from __future__ import annotations

import base64
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from looklift.plugin_catalog_config import (
    PluginCatalogConfigError,
    load_catalog_trust,
)


def _payload() -> dict:
    active = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    revoked = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
    return {
        "schema_version": 1,
        "catalog_url": "https://catalog.looklift.example/v1/catalog.json",
        "allowed_hosts": [
            "catalog.looklift.example",
            "releases.looklift.example",
        ],
        "keys": [
            {
                "id": "root-2026",
                "public_key": base64.b64encode(active).decode(),
                "status": "active",
            },
            {
                "id": "root-2025",
                "public_key": base64.b64encode(revoked).decode(),
                "status": "revoked",
            },
        ],
    }


def test_catalog_trust_loads_strict_key_rotation_contract(tmp_path):
    path = tmp_path / "plugin-catalog-trust.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")

    trust = load_catalog_trust(path)

    assert trust.catalog_url.endswith("/v1/catalog.json")
    assert trust.allowed_hosts == frozenset(
        {"catalog.looklift.example", "releases.looklift.example"}
    )
    assert set(trust.trusted_keys) == {"root-2026", "root-2025"}
    assert trust.revoked_key_ids == frozenset({"root-2025"})
    assert len(trust.trusted_keys["root-2026"]) == 32


@pytest.mark.parametrize(
    ("mutate", "message"),
    [
        (lambda value: value.update(catalog_url="http://catalog.looklift.example/v1.json"), "HTTPS"),
        (lambda value: value.update(catalog_url="https://other.example/v1.json"), "白名单"),
        (lambda value: value["keys"][0].update(status="revoked"), "有效公钥"),
        (lambda value: value["keys"][0].update(public_key="bad"), "公钥"),
        (lambda value: value.update(extra=True), "字段"),
    ],
)
def test_catalog_trust_rejects_unsafe_or_ambiguous_config(tmp_path, mutate, message):
    payload = _payload()
    mutate(payload)
    path = tmp_path / "plugin-catalog-trust.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PluginCatalogConfigError, match=message):
        load_catalog_trust(path)


def test_catalog_trust_missing_file_is_explicitly_unavailable(tmp_path):
    with pytest.raises(PluginCatalogConfigError, match="未配置"):
        load_catalog_trust(tmp_path / "missing.json")
