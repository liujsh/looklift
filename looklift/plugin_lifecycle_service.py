"""已安装 Plugin 版本的停用与重新启用业务边界。"""

from __future__ import annotations

import threading

from .capabilities import CapabilityGrantStore
from .plugin_connector_service import PluginConnectorError, PluginConnectorService
from .plugin_registry import PluginManifestError, PluginRegistry


class PluginLifecycleError(ValueError):
    """Plugin 状态变更未通过确认或安全收敛。"""


class PluginLifecycleService:
    """精确管理已安装版本；停用先断开连接并撤销匹配 Grant。"""

    def __init__(
        self,
        registry: PluginRegistry,
        grants: CapabilityGrantStore,
        connectors: PluginConnectorService,
    ) -> None:
        self._registry = registry
        self._grants = grants
        self._connectors = connectors
        self._lock = threading.RLock()

    def set_enabled(
        self,
        name: str,
        version: str,
        *,
        enabled: bool,
        confirmed: bool,
    ) -> dict:
        with self._lock:
            return self._set_enabled(
                name, version, enabled=enabled, confirmed=confirmed
            )

    def _set_enabled(
        self,
        name: str,
        version: str,
        *,
        enabled: bool,
        confirmed: bool,
    ) -> dict:
        if confirmed is not True:
            raise PluginLifecycleError("变更 Plugin 状态前必须获得用户确认")
        if not isinstance(enabled, bool):
            raise PluginLifecycleError("Plugin 启用状态无效")
        try:
            manifest = self._registry.resolve(name, version, include_disabled=True)
        except PluginManifestError as exc:
            raise PluginLifecycleError(str(exc)) from exc
        if manifest.source == "builtin":
            raise PluginLifecycleError("内置 Plugin 不能停用或重新启用")

        if not enabled:
            try:
                self._connectors.disconnect_plugin(name, version)
            except PluginConnectorError as exc:
                raise PluginLifecycleError(str(exc)) from exc
            for (subject, project_id), grant in self._grants.items():
                if subject == name and grant.version_hash == manifest.content_hash:
                    self._grants.revoke(subject, project_id=project_id)
        try:
            changed = self._registry.set_enabled(name, version, enabled=enabled)
        except PluginManifestError as exc:
            raise PluginLifecycleError(str(exc)) from exc
        return next(
            item
            for item in self._registry.list(include_disabled=True)
            if item["name"] == changed.name and item["version"] == changed.version
        )
