from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from looklift.plugin_catalog import CatalogPlugin, CatalogSnapshot, PluginCatalogError
from looklift.plugin_distribution import PluginDistributionService
from looklift.plugin_registry import PluginManifest, PluginRegistry


def _snapshot(*, stale: bool = False) -> CatalogSnapshot:
    return CatalogSnapshot(
        revision=7,
        issued_at=1_000.0,
        expires_at=2_000.0,
        key_id="root-2026",
        plugins=(
            CatalogPlugin(
                "notes",
                "1.0.0",
                "https://catalog.example/notes-1.zip",
                "a" * 64,
                "MIT",
                ("win32",),
                ("notes.read",),
            ),
            CatalogPlugin(
                "notes",
                "2.0.0",
                "https://catalog.example/notes-2.zip",
                "b" * 64,
                "MIT",
                ("win32",),
                ("notes.read", "notes.write"),
            ),
        ),
        revoked=frozenset({("notes", "1.0.0", "a" * 64)}),
        stale=stale,
    )


class FakeCache:
    def __init__(self, snapshot: CatalogSnapshot) -> None:
        self.snapshot = snapshot
        self.loads: list[bool] = []
        self.refreshes: list[tuple[str, object]] = []

    def load(self, *, allow_expired: bool = False) -> CatalogSnapshot:
        self.loads.append(allow_expired)
        return self.snapshot

    def refresh(self, url: str, *, fetch):
        self.refreshes.append((url, fetch))
        return self.snapshot


def _manifest(version: str, digest: str, *, enabled: bool = True) -> PluginManifest:
    return PluginManifest(
        2,
        "notes",
        version,
        "connector",
        "notes",
        "sidecar",
        ("text",),
        frozenset({"notes.read"}),
        digest,
        source="official-catalog",
        enabled=enabled,
    )


def test_distribution_projects_catalog_against_exact_installed_versions(tmp_path):
    registry = PluginRegistry()
    registry.install(_manifest("1.0.0", "a" * 64, enabled=False))
    cache = FakeCache(_snapshot(stale=True))
    service = PluginDistributionService(
        cache=cache,
        registry=registry,
        installer=object(),
        download_root=tmp_path,
        fetch=lambda _url, _limit: b"unused",
        current_platform="win32",
    )

    result = service.list_catalog()

    assert result["revision"] == 7
    assert result["stale"] is True
    assert cache.loads == [True]
    by_version = {item["version"]: item for item in result["plugins"]}
    assert by_version["1.0.0"] == {
        "name": "notes",
        "version": "1.0.0",
        "license": "MIT",
        "capabilities": ["notes.read"],
        "platforms": ["win32"],
        "compatible": True,
        "installed": True,
        "enabled": False,
        "package_present": True,
        "revoked": True,
        "installable": False,
        "upgrade_from": None,
    }
    assert by_version["2.0.0"]["installable"] is True
    assert by_version["2.0.0"]["upgrade_from"] == "1.0.0"


def test_distribution_install_requires_fresh_catalog_and_exact_confirmation(tmp_path):
    registry = PluginRegistry()
    cache = FakeCache(_snapshot())

    class FakeInstaller:
        def install(self, _archive_path, **kwargs):
            registry.install(_manifest(kwargs["expected_version"], kwargs["expected_sha256"]))
            return object()

    payload = b"package"
    snapshot = _snapshot()
    digest = hashlib.sha256(payload).hexdigest()
    cache.snapshot = replace(
        snapshot,
        plugins=(replace(snapshot.plugins[1], sha256=digest),),
        revoked=frozenset(),
    )
    service = PluginDistributionService(
        cache=cache,
        registry=registry,
        installer=FakeInstaller(),
        download_root=tmp_path,
        fetch=lambda _url, _limit: payload,
        current_platform="win32",
    )

    with pytest.raises(PluginCatalogError, match="确认"):
        service.install("notes", "2.0.0", confirmed=False)
    result = service.install("notes", "2.0.0", confirmed=True)

    assert result == {"name": "notes", "version": "2.0.0", "installed": True}
    assert cache.loads == [False]


def test_catalog_install_rejects_incompatible_signed_platform_before_download(tmp_path):
    cache = FakeCache(
        replace(
            _snapshot(),
            plugins=(replace(_snapshot().plugins[1], platforms=("linux",)),),
            revoked=frozenset(),
        )
    )
    fetched = []
    service = PluginDistributionService(
        cache=cache,
        registry=PluginRegistry(),
        installer=object(),
        download_root=tmp_path,
        fetch=lambda url, _limit: fetched.append(url) or b"package",
        current_platform="win32",
    )

    with pytest.raises(PluginCatalogError, match="平台"):
        service.install("notes", "2.0.0", confirmed=True)
    assert fetched == []


def test_distribution_refreshes_only_fixed_configured_catalog_url(tmp_path):
    cache = FakeCache(_snapshot())

    def fetch(_url, _limit):
        return b"catalog"

    service = PluginDistributionService(
        cache=cache,
        registry=PluginRegistry(),
        installer=object(),
        download_root=tmp_path,
        fetch=fetch,
        current_platform="win32",
        catalog_url="https://catalog.example/v1/catalog.json",
    )

    result = service.refresh()

    assert result["revision"] == 7
    assert cache.refreshes == [("https://catalog.example/v1/catalog.json", fetch)]
    assert cache.loads == [True]
