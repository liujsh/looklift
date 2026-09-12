"""Connector 配置权威与受管 MCP 会话的生命周期协调。"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any, Protocol

from .connector_registry import ConnectorConfig, ConnectorRegistry, ConnectorRegistryError


class ConnectorSessionError(RuntimeError):
    """Connector 会话启动、范围或回收失败。"""


class ConnectorClient(Protocol):
    async def connect(self) -> None: ...
    async def refresh_tools(self) -> tuple[Any, ...]: ...
    async def close(self) -> None: ...


ClientFactory = Callable[[ConnectorConfig], ConnectorClient]
RevokeHook = Callable[[str], None]


class ConnectorSessionManager:
    """每个 Connector ID 只持有一个会话；配置状态始终先于进程状态收敛。"""

    def __init__(
        self,
        registry: ConnectorRegistry,
        *,
        client_factory: ClientFactory,
        revoke_hook: RevokeHook | None = None,
    ) -> None:
        self._registry = registry
        self._factory = client_factory
        self._revoke_hook = revoke_hook
        self._clients: dict[str, ConnectorClient] = {}
        self._starting: set[str] = set()
        self._lock = threading.RLock()

    async def connect(self, connector_id: str, *, workspace_id: str) -> tuple[Any, ...]:
        with self._lock:
            config = self._scoped_config(connector_id, workspace_id)
            if not config.authorized:
                raise ConnectorSessionError("Connector 尚未授权")
            if connector_id in self._clients or connector_id in self._starting:
                raise ConnectorSessionError("Connector 会话已连接或正在启动")
            self._starting.add(connector_id)
        client: ConnectorClient | None = None
        try:
            client = self._factory(config)
            await client.connect()
            tools = await client.refresh_tools()
            frozen_tools = tuple(tools)
            with self._lock:
                latest = self._scoped_config(connector_id, workspace_id)
                if not latest.authorized:
                    raise ConnectorSessionError("Connector 启动期间授权已撤销")
                self._registry.connect(connector_id)
                self._clients[connector_id] = client
            return frozen_tools
        except Exception as exc:
            if client is not None:
                await _close_quietly(client)
            with self._lock:
                try:
                    self._registry.disconnect(connector_id)
                except ConnectorRegistryError:
                    pass
            if isinstance(exc, ConnectorSessionError):
                raise
            raise ConnectorSessionError("Connector 会话启动失败") from exc
        finally:
            with self._lock:
                self._starting.discard(connector_id)

    def get(self, connector_id: str, *, workspace_id: str) -> ConnectorClient:
        with self._lock:
            config = self._scoped_config(connector_id, workspace_id)
            client = self._clients.get(connector_id)
            if client is None or not config.authorized or not config.connected:
                raise ConnectorSessionError("Connector 会话未连接")
            return client

    async def disconnect(self, connector_id: str) -> None:
        with self._lock:
            self._registry.disconnect(connector_id)
            client = self._clients.pop(connector_id, None)
        if client is not None:
            await _close_or_raise(client)

    async def revoke(self, connector_id: str) -> None:
        with self._lock:
            self._registry.revoke(connector_id)
            client = self._clients.pop(connector_id, None)
        if self._revoke_hook is not None:
            self._revoke_hook(connector_id)
        if client is not None:
            await _close_or_raise(client)

    async def close_all(self) -> None:
        with self._lock:
            connector_ids = tuple(self._clients)
        failures = []
        for connector_id in connector_ids:
            try:
                await self.disconnect(connector_id)
            except ConnectorSessionError:
                failures.append(connector_id)
        if failures:
            raise ConnectorSessionError("部分 Connector 会话回收失败")

    def _scoped_config(self, connector_id: str, workspace_id: str) -> ConnectorConfig:
        try:
            config = self._registry.get(connector_id)
        except ConnectorRegistryError as exc:
            raise ConnectorSessionError("未知 Connector") from exc
        if config.workspace_id != workspace_id:
            raise ConnectorSessionError("Connector 不属于当前 Workspace")
        return config


async def _close_quietly(client: ConnectorClient) -> None:
    try:
        await client.close()
    except Exception:
        pass


async def _close_or_raise(client: ConnectorClient) -> None:
    try:
        await client.close()
    except Exception as exc:
        raise ConnectorSessionError("Connector 会话回收失败") from exc
