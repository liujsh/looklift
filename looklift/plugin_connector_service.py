"""插件连接的确认创建、生命周期与脱敏查询业务层。"""

from __future__ import annotations

import secrets
from collections.abc import Callable
from typing import Protocol

from .connector import ConnectorManifest
from .connector_registry import ConnectorRegistry, ConnectorRegistryError
from .connector_sessions import ConnectorRuntimeHost, ConnectorSessionError
from .plugin_registry import PluginManifestError, PluginRegistry


class PluginConnectorError(ValueError):
    """插件连接请求未通过身份、项目或确认边界。"""


class CredentialStore(Protocol):
    def put(self, provider_id: str, secret: str) -> str: ...
    def delete(self, reference: str) -> None: ...


class PluginConnectorService:
    """HTTP 无关的插件连接业务；不接收命令、入口或环境变量。"""

    def __init__(
        self,
        *,
        plugin_registry: PluginRegistry,
        connector_registry: ConnectorRegistry,
        runtime_host: ConnectorRuntimeHost,
        credential_store: CredentialStore,
        profile_delete: Callable[[str], None],
        id_factory: Callable[[], str] = lambda: f"pc-{secrets.token_hex(8)}",
    ) -> None:
        self._plugins = plugin_registry
        self._connectors = connector_registry
        self._host = runtime_host
        self._credentials = credential_store
        self._profile_delete = profile_delete
        self._id_factory = id_factory

    def create(
        self,
        *,
        plugin_name: str,
        version: str,
        service_name: str,
        project_id: str,
        account_id: str,
        credential: str | None,
        confirmed: bool,
    ) -> dict[str, object]:
        if not confirmed:
            raise PluginConnectorError("创建插件连接前必须获得用户确认")
        try:
            manifest = self._plugins.resolve(plugin_name, version)
        except PluginManifestError as exc:
            raise PluginConnectorError("Plugin 版本不可用") from exc
        services = [item for item in manifest.services if item.name == service_name]
        if len(services) != 1:
            raise PluginConnectorError("Plugin Service 不存在")
        service = services[0]
        connector_id = self._id_factory()
        credential_ref = f"secret://profile-only/{connector_id}"
        stored_credential = False
        if service.credential_env is not None:
            if not isinstance(credential, str) or not credential:
                raise PluginConnectorError("Plugin Service 需要账号凭据")
            try:
                credential_ref = self._credentials.put(connector_id, credential)
            except Exception as exc:
                raise PluginConnectorError("插件账号凭据保存失败") from exc
            stored_credential = True
        try:
            config = self._connectors.register(
                ConnectorManifest(
                    connector_id,
                    "mcp",
                    manifest.name,
                    manifest.capabilities,
                ),
                credential_ref=credential_ref,
                workspace_id=project_id,
                account_id=account_id,
                authorized=True,
                plugin_name=manifest.name,
                plugin_version=manifest.version,
                service=service.name,
            )
        except (ConnectorRegistryError, ValueError) as exc:
            if stored_credential:
                self._credentials.delete(credential_ref)
            raise PluginConnectorError("插件连接配置无效") from exc
        return config.public_dict()

    def list(self, *, project_id: str) -> tuple[dict[str, object], ...]:
        return tuple(
            item.public_dict()
            for item in self._connectors.list()
            if item.workspace_id == project_id
        )

    def connect(self, connector_id: str, *, project_id: str) -> dict[str, object]:
        self._require_project(connector_id, project_id)
        try:
            tools = self._host.connect(connector_id, workspace_id=project_id)
        except ConnectorSessionError as exc:
            raise PluginConnectorError(str(exc)) from exc
        return {"connector_id": connector_id, "connected": True, "tools": len(tools)}

    def disconnect(self, connector_id: str, *, project_id: str) -> dict[str, object]:
        self._require_project(connector_id, project_id)
        try:
            self._host.disconnect(connector_id)
        except ConnectorSessionError as exc:
            raise PluginConnectorError(str(exc)) from exc
        self._connectors.disconnect(connector_id)
        return self._connectors.get(connector_id).public_dict()

    def disconnect_plugin(self, plugin_name: str, version: str) -> int:
        """停用插件前断开该精确版本的全部在线账号，但保留登录资料。"""
        matches = [
            config
            for config in self._connectors.list()
            if config.connected
            and config.plugin_name == plugin_name
            and config.plugin_version == version
        ]
        try:
            for config in matches:
                self._host.disconnect(config.manifest.connector_id)
                self._connectors.disconnect(config.manifest.connector_id)
        except ConnectorSessionError as exc:
            raise PluginConnectorError(str(exc)) from exc
        return len(matches)

    def call_tool(
        self,
        *,
        plugin_name: str,
        plugin_version: str,
        service_name: str,
        tool_name: str,
        project_id: str,
        account_id: str,
        arguments: dict,
    ) -> dict[str, object]:
        """只通过唯一的在线项目账号调用已绑定工具。"""
        matches = [
            config
            for config in self._connectors.list()
            if config.authorized
            and config.connected
            and config.workspace_id == project_id
            and config.account_id == account_id
            and config.plugin_name == plugin_name
            and config.plugin_version == plugin_version
            and config.service == service_name
        ]
        if len(matches) != 1:
            raise PluginConnectorError("Action 没有唯一的在线绑定账号")
        return self._host.call(
            matches[0].manifest.connector_id,
            workspace_id=project_id,
            name=tool_name,
            arguments=dict(arguments),
        )

    def forget(self, connector_id: str, *, project_id: str) -> dict[str, object]:
        config = self._require_project(connector_id, project_id)
        self._connectors.revoke(connector_id)
        try:
            self._host.forget_account(
                connector_id,
                credential_delete=self._credentials.delete,
                profile_delete=self._profile_delete,
            )
        except ConnectorSessionError as exc:
            raise PluginConnectorError(str(exc)) from exc
        return {**config.public_dict(), "authorized": False, "connected": False}

    def _require_project(self, connector_id: str, project_id: str):
        try:
            config = self._connectors.get(connector_id)
        except ConnectorRegistryError as exc:
            raise PluginConnectorError("插件连接不存在") from exc
        if config.workspace_id != project_id:
            raise PluginConnectorError("插件连接不属于当前项目")
        return config
