"""受控 Plugin Manifest 注册、校验与历史版本冻结。"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace


class PluginManifestError(ValueError):
    pass


_SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
_SHA256 = re.compile(r"[0-9a-f]{64}")


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
    enabled: bool = True

    def __post_init__(self) -> None:
        if self.spec_version < 1 or not self.name or not _SEMVER.fullmatch(self.version):
            raise PluginManifestError("Plugin Manifest 身份或版本无效")
        if not _SHA256.fullmatch(self.content_hash):
            raise PluginManifestError("Plugin 内容摘要必须是小写 SHA-256")
        if self.kind not in {"skill", "template", "connector", "provider"}:
            raise PluginManifestError("Plugin kind 不受支持")
        if self.mode not in {"in_process", "sidecar", "declarative"}:
            raise PluginManifestError("Plugin mode 不受支持")
        forbidden = ("shell.", "python.", "workspace.read_original", "pixel.blackbox")
        if any(cap.startswith(forbidden) for cap in self.capabilities):
            raise PluginManifestError("禁止声明代码、原图或黑盒像素能力")


class PluginRegistry:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], PluginManifest] = {}

    def install(self, manifest: PluginManifest) -> PluginManifest:
        key = (manifest.name, manifest.version)
        if key in self._items:
            raise PluginManifestError("Plugin 版本已安装")
        self._items[key] = manifest
        return manifest

    def resolve(
        self,
        name: str,
        version: str | None = None,
        *,
        include_disabled: bool = False,
    ) -> PluginManifest:
        candidates = [
            item
            for (item_name, item_version), item in self._items.items()
            if item_name == name
            and (version is None or item_version == version)
            and (include_disabled or item.enabled)
        ]
        if not candidates:
            raise PluginManifestError("未知或已禁用 Plugin")
        return max(candidates, key=lambda item: _version_key(item.version))

    def uninstall(self, name: str, version: str) -> None:
        key = (name, version)
        try:
            self._items[key] = replace(self._items[key], enabled=False)
        except KeyError as exc:
            raise PluginManifestError("未知 Plugin") from exc

    def list(self, *, include_disabled: bool = False) -> list[dict]:
        """返回 UI 所需的脱敏 Manifest 摘要，不返回包路径或内容。"""
        items = sorted(self._items.values(), key=lambda item: (item.name, _version_key(item.version)), reverse=False)
        return [
            {
                "name": item.name,
                "version": item.version,
                "kind": item.kind,
                "task_kind": item.task_kind,
                "mode": item.mode,
                "inputs": list(item.inputs),
                "capabilities": sorted(item.capabilities),
                "content_hash": item.content_hash,
                "source": item.source,
                "enabled": item.enabled,
            }
            for item in items
            if include_disabled or item.enabled
        ]


def manifest_hash(payload: dict) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(encoded.encode()).hexdigest()


def _version_key(version: str) -> tuple[int, int, int]:
    match = _SEMVER.fullmatch(version)
    if match is None:
        raise PluginManifestError("Plugin 版本无效")
    return tuple(int(value) for value in match.groups())
