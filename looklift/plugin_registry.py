"""受控 Plugin Manifest 注册、校验与版本冻结。"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


class PluginManifestError(ValueError):
    pass


@dataclass(frozen=True)
class PluginManifest:
    spec_version: int
    name: str
    version: str
    kind: str
    task_kind: str
    mode: str
    inputs: tuple[str, ...]
    capabilities: frozenset[str]
    content_hash: str
    source: str = "local"

    def __post_init__(self) -> None:
        if self.spec_version < 1 or not self.name or not self.version:
            raise PluginManifestError("Plugin Manifest 身份无效")
        if self.kind not in {"skill", "template", "connector", "provider"}:
            raise PluginManifestError("Plugin kind 不受支持")
        if self.mode not in {"in_process", "sidecar", "declarative"}:
            raise PluginManifestError("Plugin mode 不受支持")
        if any(cap.startswith("shell.") or cap.startswith("python.") for cap in self.capabilities):
            raise PluginManifestError("禁止声明任意 Shell/Python 能力")


class PluginRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], PluginManifest] = {}

    def install(self, manifest: PluginManifest) -> PluginManifest:
        key = (manifest.name, manifest.version)
        if key in self._items:
            raise PluginManifestError("Plugin 版本已安装")
        self._items[key] = manifest
        return manifest

    def resolve(self, name: str, version: str | None = None) -> PluginManifest:
        candidates = [item for (item_name, item_version), item in self._items.items() if item_name == name and (version is None or item_version == version)]
        if not candidates:
            raise PluginManifestError("未知 Plugin")
        return sorted(candidates, key=lambda item: item.version)[-1]

    def uninstall(self, name: str, version: str) -> None:
        self._items.pop((name, version), None)


def manifest_hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
