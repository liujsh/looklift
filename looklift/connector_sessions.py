"""Connector 配置权威与受管 MCP 会话的生命周期协调。"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Callable
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any, Protocol

from .connector_registry import ConnectorConfig, ConnectorRegistry, ConnectorRegistryError


class ConnectorSessionError(RuntimeError):
    """Connector 会话启动、范围或回收失败。"""


class ConnectorClient(Protocol):
    async def connect(self) -> None: ...
    async def refresh_tools(self) -> tuple[Any, ...]: ...
    async def call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]: ...
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

    async def forget_account(
        self,
        connector_id: str,
        *,
        credential_delete: Callable[[str], None],
        profile_delete: Callable[[str], None],
    ) -> None:
        """显式忘记账号：先撤权/停进程，再删除凭据与长期 Profile。"""
        with self._lock:
            try:
                credential_ref = self._registry.get(connector_id).credential_ref
            except ConnectorRegistryError as exc:
                raise ConnectorSessionError("未知 Connector") from exc
        await self.revoke(connector_id)
        failures = 0
        for callback, value in (
            (credential_delete, credential_ref),
            (profile_delete, connector_id),
        ):
            try:
                callback(value)
            except Exception:
                failures += 1
        if failures:
            raise ConnectorSessionError("Connector 账号持久状态未完全清理")

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


class ConnectorRuntimeHost:
    """为同步 GUI/API 提供长期异步循环，避免 MCP 会话跨事件循环使用。"""

    def __init__(
        self,
        manager: ConnectorSessionManager,
        *,
        operation_timeout_seconds: float = 120,
    ) -> None:
        if operation_timeout_seconds <= 0:
            raise ConnectorSessionError("Connector Host 超时必须为正数")
        self._manager = manager
        self._timeout = operation_timeout_seconds
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._guard = threading.RLock()

    def connect(self, connector_id: str, *, workspace_id: str) -> tuple[Any, ...]:
        return self._run(self._manager.connect(connector_id, workspace_id=workspace_id))

    def call(
        self,
        connector_id: str,
        *,
        workspace_id: str,
        name: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        async def invoke() -> dict[str, Any]:
            client = self._manager.get(connector_id, workspace_id=workspace_id)
            return await client.call(name, arguments)

        return self._run(invoke())

    def disconnect(self, connector_id: str) -> None:
        self._run(self._manager.disconnect(connector_id))

    def revoke(self, connector_id: str) -> None:
        self._run(self._manager.revoke(connector_id))

    def forget_account(
        self,
        connector_id: str,
        *,
        credential_delete: Callable[[str], None],
        profile_delete: Callable[[str], None],
    ) -> None:
        self._run(
            self._manager.forget_account(
                connector_id,
                credential_delete=credential_delete,
                profile_delete=profile_delete,
            )
        )

    def close(self) -> None:
        with self._guard:
            loop = self._loop
            thread = self._thread
        if loop is None or thread is None:
            return
        try:
            self._run(self._manager.close_all())
        finally:
            loop.call_soon_threadsafe(loop.stop)
            thread.join(timeout=5)
            if thread.is_alive():
                raise ConnectorSessionError("Connector Host 事件循环未停止")
            with self._guard:
                self._loop = None
                self._thread = None

    def _run(self, coroutine):
        loop = self._ensure_loop()
        future = asyncio.run_coroutine_threadsafe(coroutine, loop)
        try:
            return future.result(timeout=self._timeout)
        except FutureTimeoutError as exc:
            future.cancel()
            raise ConnectorSessionError("Connector Host 操作超时") from exc

    def _ensure_loop(self) -> asyncio.AbstractEventLoop:
        with self._guard:
            if self._loop is not None and self._loop.is_running():
                return self._loop
            ready = threading.Event()

            def run() -> None:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                self._loop = loop
                ready.set()
                loop.run_forever()
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                if pending:
                    loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
                loop.close()

            thread = threading.Thread(
                target=run,
                daemon=True,
                name="looklift-plugin-connectors",
            )
            self._thread = thread
            thread.start()
            if not ready.wait(timeout=5) or self._loop is None:
                raise ConnectorSessionError("Connector Host 事件循环启动失败")
            return self._loop
