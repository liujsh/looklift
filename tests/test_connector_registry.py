from __future__ import annotations

import pytest

from looklift.connector import ConnectorManifest
from looklift.connector_registry import (
    ConnectorConfig,
    ConnectorRegistry,
    ConnectorRegistryError,
)


def _manifest(connector_id: str = "catalog") -> ConnectorManifest:
    return ConnectorManifest(
        connector_id=connector_id,
        protocol="https",
        receiver="catalog.example",
        capabilities=frozenset({"connector.read_catalog"}),
    )


def test_registry_requires_credential_reference_and_supports_connect_disconnect() -> None:
    registry = ConnectorRegistry()
    config = registry.register(
        _manifest(), credential_ref="keyring://looklift/catalog", authorized=True
    )
    assert config.connected is False
    connected = registry.connect("catalog")
    assert connected.connected is True
    assert registry.snapshot() == ("catalog",)
    assert registry.disconnect("catalog").connected is False
    assert registry.snapshot() == ()


def test_registry_rejects_secret_material_and_duplicate_ids() -> None:
    registry = ConnectorRegistry()
    with pytest.raises(ConnectorRegistryError, match="凭据引用"):
        registry.register(_manifest(), credential_ref="sk-secret")
    registry.register(_manifest(), credential_ref="keyring://catalog")
    with pytest.raises(ConnectorRegistryError, match="已注册"):
        registry.register(_manifest(), credential_ref="keyring://catalog")


def test_registry_connect_requires_authorization_and_snapshot_is_readonly() -> None:
    registry = ConnectorRegistry()
    registry.register(
        _manifest(), credential_ref="keyring://catalog", authorized=False
    )
    with pytest.raises(ConnectorRegistryError, match="授权"):
        registry.connect("catalog")
    registry.authorize("catalog")
    registry.connect("catalog")
    snapshot = registry.snapshot()
    assert snapshot == ("catalog",)
    with pytest.raises(AttributeError):
        snapshot.append("other")  # type: ignore[attr-defined]


def test_registry_workspace_snapshot_is_stable_and_excludes_disconnected_items() -> None:
    registry = ConnectorRegistry()
    registry.register(
        _manifest("catalog"), credential_ref="keyring://catalog", workspace_id="w1", authorized=True
    )
    registry.register(
        _manifest("camera"), credential_ref="keyring://camera", workspace_id="w2", authorized=True
    )
    registry.connect("catalog")
    registry.connect("camera")
    assert registry.workspace_snapshot("w1") == ("catalog",)
    registry.disconnect("catalog")
    assert registry.workspace_snapshot("w1") == ()


def test_config_does_not_expose_credential_reference() -> None:
    config = ConnectorConfig(
        manifest=_manifest(), credential_ref="keyring://catalog", connected=True
    )
    public = config.public_dict()
    assert public["connector_id"] == "catalog"
    assert "credential_ref" not in public


def test_registry_persists_connection_state_without_exposing_secret(tmp_path) -> None:
    registry = ConnectorRegistry(root=tmp_path)
    registry.register(
        _manifest(), credential_ref="keyring://looklift/catalog", workspace_id="project-a", authorized=True
    )
    registry.connect("catalog")

    restored = ConnectorRegistry(root=tmp_path)
    assert restored.workspace_snapshot("project-a") == ()
    assert restored.get("catalog").authorized is True
    assert restored.get("catalog").connected is False
    assert "credential_ref" not in restored.public_list()[0]
    assert "keyring://looklift/catalog" in (tmp_path / "connectors.json").read_text(encoding="utf-8")


def test_registry_keeps_accounts_isolated_by_connection(tmp_path) -> None:
    registry = ConnectorRegistry(root=tmp_path)
    registry.register(
        _manifest("notes-main"),
        credential_ref="keyring://notes/main",
        workspace_id="project-a",
        account_id="account-main",
        authorized=True,
    )
    registry.register(
        _manifest("notes-work"),
        credential_ref="keyring://notes/work",
        workspace_id="project-a",
        account_id="account-work",
        authorized=True,
    )
    registry.connect("notes-main")
    registry.connect("notes-work")

    assert registry.account_snapshot("project-a", receiver="catalog.example") == (
        ("notes-main", "account-main"),
        ("notes-work", "account-work"),
    )
    assert registry.get("notes-main").account_id == "account-main"
    assert ConnectorRegistry(root=tmp_path).get("notes-work").account_id == "account-work"


def test_registry_rejects_unsafe_account_id() -> None:
    registry = ConnectorRegistry()
    with pytest.raises(ConnectorRegistryError, match="账号"):
        registry.register(
            _manifest(),
            credential_ref="keyring://catalog",
            account_id="../cookie-profile",
        )
