from __future__ import annotations

import pytest

from looklift.capabilities import CapabilityGrant, CapabilityGrantStore
from looklift.plugin_lifecycle_service import (
    PluginLifecycleError,
    PluginLifecycleService,
)
from looklift.plugin_registry import PluginManifest, PluginRegistry


class FakeConnectors:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def disconnect_plugin(self, name: str, version: str) -> int:
        self.calls.append((name, version))
        return 2


def _manifest(*, source: str = "catalog") -> PluginManifest:
    return PluginManifest(
        2,
        "notes",
        "1.0.0",
        "connector",
        "notes",
        "sidecar",
        ("text",),
        frozenset({"notes.read"}),
        "a" * 64,
        source=source,
    )


def test_disable_disconnects_accounts_revokes_matching_grants_and_preserves_history():
    registry = PluginRegistry()
    registry.install(_manifest())
    grants = CapabilityGrantStore()
    grants.put(CapabilityGrant("notes", frozenset({"notes.read"}), "project-a", "a" * 64))
    connectors = FakeConnectors()
    service = PluginLifecycleService(registry, grants, connectors)

    result = service.set_enabled("notes", "1.0.0", enabled=False, confirmed=True)

    assert result["enabled"] is False
    assert connectors.calls == [("notes", "1.0.0")]
    assert grants.active_for("notes", project_id="project-a") is None
    assert registry.resolve("notes", "1.0.0", include_disabled=True).enabled is False


def test_reenable_does_not_restore_grants_or_connect_accounts():
    registry = PluginRegistry()
    registry.install(_manifest())
    registry.set_enabled("notes", "1.0.0", enabled=False)
    grants = CapabilityGrantStore()
    connectors = FakeConnectors()
    service = PluginLifecycleService(registry, grants, connectors)

    result = service.set_enabled("notes", "1.0.0", enabled=True, confirmed=True)

    assert result["enabled"] is True
    assert connectors.calls == []
    assert grants.active_for("notes", project_id="project-a") is None


def test_lifecycle_requires_confirmation_and_protects_builtin_plugin():
    registry = PluginRegistry()
    registry.install(_manifest(source="builtin"))
    service = PluginLifecycleService(registry, CapabilityGrantStore(), FakeConnectors())

    with pytest.raises(PluginLifecycleError, match="确认"):
        service.set_enabled("notes", "1.0.0", enabled=False, confirmed=False)
    with pytest.raises(PluginLifecycleError, match="内置"):
        service.set_enabled("notes", "1.0.0", enabled=False, confirmed=True)
