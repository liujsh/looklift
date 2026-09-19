"""从已安装包与 Connector 绑定构造受控 MCP Runtime。"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Protocol

from .connector_registry import ConnectorConfig
from .plugin_mcp_client import ManagedMcpClient, McpTransport, StdioMcpTransport
from .plugin_registry import PluginManifestError, PluginRegistry, PluginService


class PluginRuntimeError(RuntimeError):
    """插件连接绑定、入口完整性或凭据解析失败。"""


CredentialResolver = Callable[[str], str | None]


class TransportBuilder(Protocol):
    def __call__(
        self,
        command: Sequence[str],
        cwd: str,
        environment: Mapping[str, str],
    ) -> McpTransport: ...


_BASE_ENVIRONMENT = frozenset({"SYSTEMROOT", "WINDIR", "TEMP", "TMP", "LANG"})
_CONNECTION_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class PluginProfileStore:
    """账号长期 Profile 目录；仅显式忘记账号时删除。"""

    def __init__(self, root: Path) -> None:
        self._root = (Path(root).resolve() / "plugin-state").resolve()

    def prepare(self, connector_id: str) -> Path:
        target = self._target(connector_id)
        target.mkdir(parents=True, exist_ok=True)
        return target

    def delete(self, connector_id: str) -> None:
        target = self._target(connector_id)
        if target.exists():
            shutil.rmtree(target)

    def _target(self, connector_id: str) -> Path:
        if not isinstance(connector_id, str) or not _CONNECTION_ID.fullmatch(connector_id):
            raise PluginRuntimeError("Connector ID 不安全")
        target = (self._root / connector_id).resolve()
        if target.parent != self._root:
            raise PluginRuntimeError("Plugin 账号 Profile 路径无效")
        return target


class StdioPluginClientFactory:
    """只从已登记服务构造 stdio Client；不接受请求侧命令或环境变量。"""

    def __init__(
        self,
        *,
        install_root: Path,
        registry: PluginRegistry,
        credential_resolver: CredentialResolver,
        transport_builder: TransportBuilder | None = None,
        base_environment: Mapping[str, str] | None = None,
    ) -> None:
        self._root = Path(install_root).resolve()
        self._plugins = self._root / "plugins"
        self._profiles = PluginProfileStore(self._root)
        self._registry = registry
        self._credentials = credential_resolver
        self._transport_builder = transport_builder or _build_stdio_transport
        source = os.environ if base_environment is None else base_environment
        self._base_environment = {
            key: value
            for key, value in source.items()
            if key.upper() in _BASE_ENVIRONMENT and isinstance(value, str)
        }

    def __call__(self, config: ConnectorConfig) -> ManagedMcpClient:
        if not config.plugin_name or not config.plugin_version or not config.service:
            raise PluginRuntimeError("Connector 缺少完整 Plugin Service 绑定")
        try:
            manifest = self._registry.resolve(config.plugin_name, config.plugin_version)
        except PluginManifestError as exc:
            raise PluginRuntimeError("Connector 绑定的 Plugin 不可用") from exc
        service = _resolve_service(manifest.services, config.service)
        package = (self._plugins / manifest.name / manifest.version).resolve()
        entrypoint = (package / Path(*PurePosixPath(service.entrypoint).parts)).resolve()
        if package not in entrypoint.parents or not entrypoint.is_file():
            raise PluginRuntimeError("Plugin Service 入口不在已安装包内")
        if _file_sha256(entrypoint) != service.entrypoint_sha256:
            raise PluginRuntimeError("Plugin Service 入口摘要不匹配")
        profile = self._profiles.prepare(config.manifest.connector_id)
        environment = {
            **self._base_environment,
            "LOOKLIFT_PLUGIN_PROFILE": str(profile),
            "LOOKLIFT_PLUGIN_ACCOUNT": config.account_id,
        }
        if service.credential_env is not None:
            try:
                credential = self._credentials(config.credential_ref)
            except Exception as exc:
                raise PluginRuntimeError("Plugin 凭据解析失败") from exc
            if not credential:
                raise PluginRuntimeError("Plugin 凭据不存在")
            environment[service.credential_env] = credential
        transport = self._transport_builder(
            (str(entrypoint), *service.arguments),
            str(package),
            environment,
        )
        metadata = {
            tool.name: {
                "capabilities": sorted(tool.capabilities),
                "risk": tool.risk,
                "aliases": list(tool.aliases),
                "task_tags": list(tool.task_tags),
                "requires_account": tool.requires_account,
                "confirmation_fields": [
                    field.public_dict() for field in tool.confirmation_fields
                ],
            }
            for tool in self._registry.tools_for(manifest.name, manifest.version)
            if tool.service == service.name
        }
        return ManagedMcpClient(
            transport,
            manifest=manifest,
            service=service.name,
            tool_metadata=metadata,
        )


def _resolve_service(
    services: tuple[PluginService, ...], name: str
) -> PluginService:
    matches = [service for service in services if service.name == name]
    if len(matches) != 1:
        raise PluginRuntimeError("Connector 绑定的 Plugin Service 不存在")
    return matches[0]


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        raise PluginRuntimeError("Plugin Service 入口不可读") from exc
    return digest.hexdigest()


def _build_stdio_transport(
    command: Sequence[str], cwd: str, environment: Mapping[str, str]
) -> McpTransport:
    return StdioMcpTransport(command, cwd=cwd, environment=environment)
