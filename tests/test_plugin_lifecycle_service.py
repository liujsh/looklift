from __future__ import annotations

from pathlib import Path

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


def test_cleanup_removes_disabled_package_but_preserves_registry_history(tmp_path: Path):
    registry = PluginRegistry(tmp_path / "state")
    registry.install(_manifest())
    registry.set_enabled("notes", "1.0.0", enabled=False)
    package = tmp_path / "packages" / "notes" / "1.0.0"
    package.mkdir(parents=True)
    (package / "runtime.exe").write_bytes(b"runtime")
    service = PluginLifecycleService(
        registry,
        CapabilityGrantStore(),
        FakeConnectors(),
        package_root=tmp_path / "packages",
    )

    result = service.cleanup("notes", "1.0.0", confirmed=True)

    assert result["installed"] is False
    assert result["enabled"] is False
    assert not package.exists()
    historical = PluginRegistry(tmp_path / "state").resolve(
        "notes", "1.0.0", include_disabled=True
    )
    assert historical.installed is False
    with pytest.raises(PluginLifecycleError, match="已清理"):
        service.set_enabled("notes", "1.0.0", enabled=True, confirmed=True)


def test_cleanup_requires_disabled_exact_version_and_confirmation(tmp_path: Path):
    registry = PluginRegistry()
    registry.install(_manifest())
    package = tmp_path / "packages" / "notes" / "1.0.0"
    package.mkdir(parents=True)
    service = PluginLifecycleService(
        registry,
        CapabilityGrantStore(),
        FakeConnectors(),
        package_root=tmp_path / "packages",
    )

    with pytest.raises(PluginLifecycleError, match="确认"):
        service.cleanup("notes", "1.0.0", confirmed=False)
    with pytest.raises(PluginLifecycleError, match="先停用"):
        service.cleanup("notes", "1.0.0", confirmed=True)
    assert package.exists()


def test_cleanup_delete_failure_keeps_package_quarantined_and_not_runnable(
    tmp_path: Path, monkeypatch
):
    registry = PluginRegistry()
    registry.install(_manifest())
    registry.set_enabled("notes", "1.0.0", enabled=False)
    package_root = tmp_path / "packages"
    package = package_root / "notes" / "1.0.0"
    package.mkdir(parents=True)
    service = PluginLifecycleService(
        registry,
        CapabilityGrantStore(),
        FakeConnectors(),
        package_root=package_root,
    )

    def fail_delete(_path):
        raise OSError("locked")

    monkeypatch.setattr("looklift.plugin_lifecycle_service.shutil.rmtree", fail_delete)

    with pytest.raises(PluginLifecycleError, match="已隔离"):
        service.cleanup("notes", "1.0.0", confirmed=True)

    assert not package.exists()
    assert registry.resolve(
        "notes", "1.0.0", include_disabled=True
    ).installed is False
    assert any((package_root / ".cleanup").iterdir())
