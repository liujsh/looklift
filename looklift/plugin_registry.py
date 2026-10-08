"""受控 Plugin Manifest 注册、校验与历史版本冻结。"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Iterable

if TYPE_CHECKING:
    from .plugin_tools import PluginTool


class PluginManifestError(ValueError):
    pass


_SEMVER = re.compile(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)")
_SHA256 = re.compile(r"[0-9a-f]{64}")
_SAFE_COMPONENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
_SAFE_ENV = re.compile(r"[A-Z][A-Z0-9_]{0,63}")


@dataclass(frozen=True)
class PluginService:
    """审核后可持久化的包内 MCP Service 启动契约。"""

    name: str
    transport: str
    entrypoint: str
    entrypoint_sha256: str
    arguments: tuple[str, ...] = ()
    credential_env: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", tuple(self.arguments))
        path = PurePosixPath(self.entrypoint)
        if (
            not _SAFE_COMPONENT.fullmatch(self.name)
            or self.transport != "stdio"
            or path.is_absolute()
            or not path.parts
            or any(part in {"", ".", ".."} for part in path.parts)
            or any(not _SAFE_COMPONENT.fullmatch(part) for part in path.parts)
            or "\\" in self.entrypoint
            or not _SHA256.fullmatch(self.entrypoint_sha256)
        ):
            raise PluginManifestError("Plugin Service 启动契约无效")
        if len(self.arguments) > 64 or any(
            not isinstance(value, str)
            or not value
            or len(value) > 4096
            or "\x00" in value
            for value in self.arguments
        ):
            raise PluginManifestError("Plugin Service 参数无效")
        if self.credential_env is not None and not _SAFE_ENV.fullmatch(self.credential_env):
            raise PluginManifestError("Plugin Service 凭据环境变量无效")


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
    installed: bool = True
    aliases: tuple[str, ...] = ()
    description: str = ""
    services: tuple[PluginService, ...] = ()

    def __post_init__(self) -> None:
        if self.spec_version < 1 or not self.name or not _SEMVER.fullmatch(self.version):
            raise PluginManifestError("Plugin Manifest 身份或版本无效")
        if (
            not isinstance(self.enabled, bool)
            or not isinstance(self.installed, bool)
            or (self.enabled and not self.installed)
        ):
            raise PluginManifestError("Plugin 启用与安装状态无效")
        if not _SHA256.fullmatch(self.content_hash):
            raise PluginManifestError("Plugin 内容摘要必须是小写 SHA-256")
        if self.kind not in {"skill", "template", "connector", "provider"}:
            raise PluginManifestError("Plugin kind 不受支持")
        if self.mode not in {"in_process", "sidecar", "declarative"}:
            raise PluginManifestError("Plugin mode 不受支持")
        forbidden = ("shell.", "python.", "workspace.read_original", "pixel.blackbox")
        if any(cap.startswith(forbidden) for cap in self.capabilities):
            raise PluginManifestError("禁止声明代码、原图或黑盒像素能力")
        if any(not isinstance(value, str) or not value.strip() for value in self.aliases):
            raise PluginManifestError("Plugin 别名必须是非空文本")
        object.__setattr__(self, "services", tuple(self.services))
        if len({service.name for service in self.services}) != len(self.services):
            raise PluginManifestError("Plugin Service 名称重复")


class PluginRegistry:
    """Plugin Manifest 与实时工具目录的唯一权威，可选落盘。"""

    def __init__(self, root: Path | None = None) -> None:
        self._items: dict[tuple[str, str], PluginManifest] = {}
        self._tools: dict[tuple[str, str], tuple["PluginTool", ...]] = {}
        self._root = Path(root) if root is not None else None
        if self._root is not None:
            self._load()

    def install(
        self,
        manifest: PluginManifest,
        *,
        tools: Iterable["PluginTool"] = (),
    ) -> PluginManifest:
        key = (manifest.name, manifest.version)
        if key in self._items:
            raise PluginManifestError("Plugin 版本已安装")
        frozen_tools = tuple(tools)
        self._validate_tools(manifest, frozen_tools)
        self._items[key] = manifest
        self._tools[key] = frozen_tools
        self._save()
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
            and (include_disabled or (item.enabled and item.installed))
        ]
        if not candidates:
            raise PluginManifestError("未知或已禁用 Plugin")
        return max(candidates, key=lambda item: _version_key(item.version))

    def uninstall(self, name: str, version: str) -> None:
        self.set_enabled(name, version, enabled=False)

    def set_enabled(self, name: str, version: str, *, enabled: bool) -> PluginManifest:
        if not isinstance(enabled, bool):
            raise PluginManifestError("Plugin 启用状态无效")
        key = (name, version)
        try:
            current = self._items[key]
        except KeyError as exc:
            raise PluginManifestError("未知 Plugin") from exc
        if enabled and not current.installed:
            raise PluginManifestError("Plugin 包已清理，不能重新启用")
        self._items[key] = replace(current, enabled=enabled)
        self._save()
        return self._items[key]

    def set_installed(self, name: str, version: str, *, installed: bool) -> PluginManifest:
        """记录精确版本的包是否仍在磁盘，历史 Manifest 始终保留。"""
        if not isinstance(installed, bool):
            raise PluginManifestError("Plugin 安装状态无效")
        key = (name, version)
        try:
            current = self._items[key]
        except KeyError as exc:
            raise PluginManifestError("未知 Plugin") from exc
        if not installed and current.enabled:
            raise PluginManifestError("清理 Plugin 包前必须先停用")
        self._items[key] = replace(current, installed=installed)
        self._save()
        return self._items[key]

    def tools_for(self, name: str, version: str | None = None) -> tuple["PluginTool", ...]:
        manifest = self.resolve(name, version)
        return self._tools.get((manifest.name, manifest.version), ())

    def all_tools(self) -> tuple["PluginTool", ...]:
        tools: list["PluginTool"] = []
        for manifest in self._items.values():
            if manifest.enabled and manifest.installed:
                tools.extend(self._tools.get((manifest.name, manifest.version), ()))
        return tuple(sorted(tools, key=lambda item: item.identity))

    def replace_tools(
        self,
        name: str,
        version: str,
        tools: Iterable["PluginTool"],
    ) -> None:
        manifest = self.resolve(name, version)
        frozen = tuple(tools)
        self._validate_tools(manifest, frozen)
        self._tools[(name, version)] = frozen
        self._save()

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
                "installed": item.installed,
                "aliases": list(item.aliases),
                "description": item.description,
                "services": [
                    {
                        "name": service.name,
                        "transport": service.transport,
                        "requires_credential": service.credential_env is not None,
                    }
                    for service in item.services
                ],
            }
            for item in items
            if include_disabled or item.enabled
        ]

    def _validate_tools(
        self,
        manifest: PluginManifest,
        tools: tuple["PluginTool", ...],
    ) -> None:
        identities: set[str] = set()
        for tool in tools:
            if (
                tool.plugin_name != manifest.name
                or tool.plugin_version != manifest.version
                or tool.plugin_hash != manifest.content_hash
            ):
                raise PluginManifestError("工具身份与 Plugin Manifest 不一致")
            if not tool.capabilities <= manifest.capabilities:
                raise PluginManifestError("工具能力不能超过 Plugin 声明")
            if manifest.services and tool.service not in {item.name for item in manifest.services}:
                raise PluginManifestError("工具引用了未声明的 Plugin Service")
            if tool.identity in identities:
                raise PluginManifestError("Plugin 工具身份重复")
            identities.add(tool.identity)

    @property
    def _storage_path(self) -> Path | None:
        return self._root / "registry.json" if self._root is not None else None

    def _save(self) -> None:
        path = self._storage_path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = []
        for key, manifest in sorted(self._items.items()):
            payload.append(
                {
                    "manifest": {
                        "spec_version": manifest.spec_version,
                        "name": manifest.name,
                        "version": manifest.version,
                        "kind": manifest.kind,
                        "task_kind": manifest.task_kind,
                        "mode": manifest.mode,
                        "inputs": list(manifest.inputs),
                        "capabilities": sorted(manifest.capabilities),
                        "content_hash": manifest.content_hash,
                        "source": manifest.source,
                        "enabled": manifest.enabled,
                        "installed": manifest.installed,
                        "aliases": list(manifest.aliases),
                        "description": manifest.description,
                        "services": [
                            {
                                "name": service.name,
                                "transport": service.transport,
                                "entrypoint": service.entrypoint,
                                "entrypoint_sha256": service.entrypoint_sha256,
                                "arguments": list(service.arguments),
                                "credential_env": service.credential_env,
                            }
                            for service in manifest.services
                        ],
                    },
                    "tools": [tool.as_storage_dict() for tool in self._tools.get(key, ())],
                }
            )
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        temporary.replace(path)

    def _load(self) -> None:
        path = self._storage_path
        if path is None or not path.exists():
            return
        from .plugin_tools import PluginTool

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError
            for item in payload:
                raw = item["manifest"]
                manifest = PluginManifest(
                    spec_version=raw["spec_version"],
                    name=raw["name"],
                    version=raw["version"],
                    kind=raw["kind"],
                    task_kind=raw["task_kind"],
                    mode=raw["mode"],
                    inputs=tuple(raw["inputs"]),
                    capabilities=frozenset(raw["capabilities"]),
                    content_hash=raw["content_hash"],
                    source=raw.get("source", "local"),
                    enabled=raw.get("enabled", True),
                    installed=raw.get("installed", True),
                    aliases=tuple(raw.get("aliases", ())),
                    description=raw.get("description", ""),
                    services=tuple(
                        PluginService(
                            name=service["name"],
                            transport=service["transport"],
                            entrypoint=service["entrypoint"],
                            entrypoint_sha256=service["entrypoint_sha256"],
                            arguments=tuple(service.get("arguments", ())),
                            credential_env=service.get("credential_env"),
                        )
                        for service in raw.get("services", ())
                    ),
                )
                tools = tuple(PluginTool.from_storage_dict(value) for value in item.get("tools", ()))
                self._validate_tools(manifest, tools)
                key = (manifest.name, manifest.version)
                self._items[key] = manifest
                self._tools[key] = tools
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise PluginManifestError("Plugin 持久化目录损坏") from exc


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
