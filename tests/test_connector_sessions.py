from __future__ import annotations

import asyncio

import pytest

from looklift.connector import ConnectorManifest
from looklift.connector_registry import ConnectorRegistry
from looklift.connector_sessions import ConnectorSessionError, ConnectorSessionManager


class FakeClient:
    def __init__(self, *, fail_connect=False, close_hook=None):
        self.fail_connect = fail_connect
        self.close_hook = close_hook
        self.connected = 0
        self.refreshed = 0
        self.closed = 0

    async def connect(self):
        self.connected += 1
        if self.fail_connect:
            raise RuntimeError("boom")

    async def refresh_tools(self):
        self.refreshed += 1
        return ("tool",)

    async def close(self):
        self.closed += 1
        if self.close_hook:
            self.close_hook()


def _registry(tmp_path):
    registry = ConnectorRegistry(root=tmp_path)
    registry.register(
        ConnectorManifest("notes", "mcp", "notes.example", frozenset({"notes.read"})),
        credential_ref="keyring://looklift/notes",
        workspace_id="project-a",
        authorized=True,
    )
    return registry


def test_session_connects_and_publishes_online_state_only_after_handshake(tmp_path):
    registry = _registry(tmp_path)
    client = FakeClient()
    manager = ConnectorSessionManager(registry, client_factory=lambda _config: client)

    tools = asyncio.run(manager.connect("notes", workspace_id="project-a"))

    assert tools == ("tool",)
    assert registry.get("notes").connected is True
    assert manager.get("notes", workspace_id="project-a") is client


def test_failed_session_start_is_closed_and_never_marked_online(tmp_path):
    registry = _registry(tmp_path)
    client = FakeClient(fail_connect=True)
    manager = ConnectorSessionManager(registry, client_factory=lambda _config: client)

    with pytest.raises(ConnectorSessionError, match="启动失败"):
        asyncio.run(manager.connect("notes", workspace_id="project-a"))

    assert client.closed == 1
    assert registry.get("notes").connected is False


def test_disconnect_and_revoke_update_authority_before_closing_session(tmp_path):
    registry = _registry(tmp_path)
    observed = []
    client = FakeClient(
        close_hook=lambda: observed.append(registry.get("notes").connected)
    )
    revoked = []
    manager = ConnectorSessionManager(
        registry,
        client_factory=lambda _config: client,
        revoke_hook=lambda connector_id: revoked.append(connector_id),
    )
    asyncio.run(manager.connect("notes", workspace_id="project-a"))

    asyncio.run(manager.revoke("notes"))

    assert observed == [False]
    assert revoked == ["notes"]
    assert registry.get("notes").authorized is False
    with pytest.raises(ConnectorSessionError, match="未连接"):
        manager.get("notes", workspace_id="project-a")


def test_session_access_is_workspace_scoped(tmp_path):
    registry = _registry(tmp_path)
    manager = ConnectorSessionManager(
        registry, client_factory=lambda _config: FakeClient()
    )
    with pytest.raises(ConnectorSessionError, match="Workspace"):
        asyncio.run(manager.connect("notes", workspace_id="project-b"))


def test_authorization_revoked_during_handshake_prevents_session_publish(tmp_path):
    registry = _registry(tmp_path)

    class RevokingClient(FakeClient):
        async def refresh_tools(self):
            registry.revoke("notes")
            return await super().refresh_tools()

    client = RevokingClient()
    manager = ConnectorSessionManager(registry, client_factory=lambda _config: client)

    with pytest.raises(ConnectorSessionError, match="授权已撤销"):
        asyncio.run(manager.connect("notes", workspace_id="project-a"))

    assert client.closed == 1
    assert registry.get("notes").authorized is False
    assert registry.get("notes").connected is False
