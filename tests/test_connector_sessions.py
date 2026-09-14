from __future__ import annotations

import asyncio

import pytest

from looklift.connector import ConnectorManifest
from looklift.connector_registry import ConnectorRegistry
from looklift.connector_sessions import (
    ConnectorRuntimeHost,
    ConnectorSessionError,
    ConnectorSessionManager,
)


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

    async def call(self, name, arguments):
        return {"name": name, "arguments": dict(arguments)}


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


def test_forget_account_revokes_and_closes_before_removing_persistent_state(tmp_path):
    registry = _registry(tmp_path)
    order = []
    client = FakeClient(
        close_hook=lambda: order.append(("close", registry.get("notes").authorized))
    )
    manager = ConnectorSessionManager(registry, client_factory=lambda _config: client)
    asyncio.run(manager.connect("notes", workspace_id="project-a"))

    asyncio.run(
        manager.forget_account(
            "notes",
            credential_delete=lambda reference: order.append(
                ("credential", reference)
            ),
            profile_delete=lambda connector_id: order.append(
                ("profile", connector_id)
            ),
        )
    )

    assert order == [
        ("close", False),
        ("credential", "keyring://looklift/notes"),
        ("profile", "notes"),
    ]


def test_disconnect_preserves_account_credential_and_profile(tmp_path):
    registry = _registry(tmp_path)
    manager = ConnectorSessionManager(
        registry, client_factory=lambda _config: FakeClient()
    )
    asyncio.run(manager.connect("notes", workspace_id="project-a"))

    asyncio.run(manager.disconnect("notes"))

    assert registry.get("notes").authorized is True
    assert registry.get("notes").credential_ref == "keyring://looklift/notes"


def test_runtime_host_keeps_connect_call_and_close_on_one_event_loop(tmp_path):
    registry = _registry(tmp_path)
    loop_ids = []

    class LoopAwareClient(FakeClient):
        async def connect(self):
            loop_ids.append(id(asyncio.get_running_loop()))
            await super().connect()

        async def call(self, name, arguments):
            loop_ids.append(id(asyncio.get_running_loop()))
            return await super().call(name, arguments)

        async def close(self):
            loop_ids.append(id(asyncio.get_running_loop()))
            await super().close()

    manager = ConnectorSessionManager(
        registry, client_factory=lambda _config: LoopAwareClient()
    )
    host = ConnectorRuntimeHost(manager)
    try:
        assert host.connect("notes", workspace_id="project-a") == ("tool",)
        assert host.call(
            "notes", workspace_id="project-a", name="list_notes", arguments={"limit": 1}
        ) == {"name": "list_notes", "arguments": {"limit": 1}}
        host.disconnect("notes")
    finally:
        host.close()

    assert len(set(loop_ids)) == 1
