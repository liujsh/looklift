"""已安装 Plugin 版本的停用与重新启用业务边界。"""

from __future__ import annotations

import os
import secrets
import shutil
import threading
from pathlib import Path

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
        *,
        package_root: Path | None = None,
    ) -> None:
        self._registry = registry
        self._grants = grants
        self._connectors = connectors
        self._package_root = Path(package_root).resolve() if package_root is not None else None
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
        if enabled and not manifest.installed:
            raise PluginLifecycleError("Plugin 包已清理，不能重新启用")

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

    def cleanup(self, name: str, version: str, *, confirmed: bool) -> dict:
        """删除已停用版本的可执行包，同时保留 Registry 审计快照。"""
        with self._lock:
            if confirmed is not True:
                raise PluginLifecycleError("清理 Plugin 包前必须获得用户确认")
            if self._package_root is None:
                raise PluginLifecycleError("Plugin 包目录未配置")
            try:
                manifest = self._registry.resolve(name, version, include_disabled=True)
            except PluginManifestError as exc:
                raise PluginLifecycleError(str(exc)) from exc
            if manifest.source == "builtin":
                raise PluginLifecycleError("内置 Plugin 不能清理")
            if manifest.enabled:
                raise PluginLifecycleError("清理 Plugin 包前必须先停用")
            if not manifest.installed:
                raise PluginLifecycleError("Plugin 包已清理")

            target = (self._package_root / name / version).resolve()
            expected_parent = (self._package_root / name).resolve()
            if (
                target.parent != expected_parent
                or expected_parent.parent != self._package_root
                or not target.is_dir()
                or target.is_symlink()
            ):
                raise PluginLifecycleError("Plugin 包目录不存在或不安全")
            cleanup_root = (self._package_root / ".cleanup").resolve()
            cleanup_root.mkdir(parents=True, exist_ok=True)
            quarantine = cleanup_root / secrets.token_hex(16)
            try:
                os.replace(target, quarantine)
            except OSError as exc:
                raise PluginLifecycleError("Plugin 包无法移入安全清理区") from exc
            try:
                changed = self._registry.set_installed(name, version, installed=False)
            except PluginManifestError as exc:
                if quarantine.exists():
                    try:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(quarantine, target)
                    except OSError:
                        pass
                raise PluginLifecycleError("Plugin 包安全清理失败") from exc
            try:
                shutil.rmtree(quarantine)
            except OSError as exc:
                # 可执行包已经移出固定运行路径，保持“已清理”状态可防止残包被重新启用。
                raise PluginLifecycleError("Plugin 包已隔离，但残留文件清理失败") from exc
            return next(
                item
                for item in self._registry.list(include_disabled=True)
                if item["name"] == changed.name and item["version"] == changed.version
            )
