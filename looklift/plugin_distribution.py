"""验签目录与已安装 Plugin 状态之间的分发业务投影。"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Protocol

from .plugin_catalog import (
    CatalogFetcher,
    CatalogSnapshot,
    PluginCatalogError,
    install_catalog_plugin,
)
from .plugin_registry import PluginManifestError, PluginRegistry


class CatalogCache(Protocol):
    def load(self, *, allow_expired: bool = False) -> CatalogSnapshot: ...


_STABLE_SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")


class PluginDistributionService:
    """只消费已验签目录；列表允许过期缓存，安装必须使用有效快照。"""

    def __init__(
        self,
        *,
        cache: CatalogCache,
        registry: PluginRegistry,
        installer: Any,
        download_root: Path,
        fetch: CatalogFetcher,
        current_platform: str,
    ) -> None:
        self._cache = cache
        self._registry = registry
        self._installer = installer
        self._download_root = Path(download_root)
        self._fetch = fetch
        self._platform = current_platform

    def list_catalog(self) -> dict[str, object]:
        snapshot = self._cache.load(allow_expired=True)
        installed = self._registry.list(include_disabled=True)
        exact = {(item["name"], item["version"]): item for item in installed}
        plugins: list[dict[str, object]] = []
        for plugin in snapshot.plugins:
            historical = exact.get((plugin.name, plugin.version))
            revoked = (plugin.name, plugin.version, plugin.sha256) in snapshot.revoked
            compatible = self._platform in plugin.platforms
            upgrade_from = self._upgrade_source(
                plugin.name, plugin.version, installed
            )
            plugins.append(
                {
                    "name": plugin.name,
                    "version": plugin.version,
                    "license": plugin.license,
                    "capabilities": list(plugin.capabilities),
                    "platforms": list(plugin.platforms),
                    "compatible": compatible,
                    "installed": historical is not None,
                    "enabled": bool(historical and historical["enabled"]),
                    "package_present": bool(
                        historical and historical.get("installed", True)
                    ),
                    "revoked": revoked,
                    "installable": historical is None and compatible and not revoked,
                    "upgrade_from": upgrade_from,
                }
            )
        return {
            "revision": snapshot.revision,
            "issued_at": snapshot.issued_at,
            "expires_at": snapshot.expires_at,
            "stale": snapshot.stale,
            "plugins": plugins,
        }

    def install(self, name: str, version: str, *, confirmed: bool) -> dict[str, object]:
        if confirmed is not True:
            raise PluginCatalogError("目录插件安装前必须获得用户确认")
        snapshot = self._cache.load()
        plugin = snapshot.resolve(name, version)
        if self._platform not in plugin.platforms:
            raise PluginCatalogError("目录插件与当前平台不兼容")
        try:
            self._registry.resolve(name, version, include_disabled=True)
        except PluginManifestError:
            pass
        else:
            raise PluginCatalogError("Plugin 版本已有历史记录，不能重复安装")
        install_catalog_plugin(
            snapshot,
            name,
            version,
            installer=self._installer,
            download_root=self._download_root,
            fetch=self._fetch,
            confirmed=True,
            current_platform=self._platform,
        )
        manifest = self._registry.resolve(name, version)
        return {"name": manifest.name, "version": manifest.version, "installed": True}

    @staticmethod
    def _upgrade_source(
        name: str, target_version: str, installed: list[dict]
    ) -> str | None:
        target = _version_key(target_version)
        candidates = [
            item["version"]
            for item in installed
            if item["name"] == name
            and item.get("installed", True)
            and _version_key(item["version"]) < target
        ]
        return max(candidates, key=_version_key) if candidates else None


def _version_key(version: str) -> tuple[int, int, int]:
    match = _STABLE_SEMVER.fullmatch(version)
    if match is None:
        raise PluginCatalogError("目录插件版本不受支持")
    return tuple(int(value) for value in match.groups())
