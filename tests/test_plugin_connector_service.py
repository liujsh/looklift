from __future__ import annotations

import pytest

from looklift.connector_registry import ConnectorRegistry
from looklift.plugin_connector_service import (
    PluginConnectorError,
    PluginConnectorService,
)
from looklift.plugin_registry import PluginManifest, PluginRegistry, PluginService


class FakeCredentials:
    def __init__(self):
        self.values = {}

    def put(self, key, secret):
        self.values[key] = secret
        return f"dpapi://{key}"

    def delete(self, reference):
        self.values.pop(reference.removeprefix("dpapi://"), None)


class FakeHost:
    def __init__(self):
        self.calls = []

    def connect(self, connector_id, *, workspace_id):
        self.calls.append(("connect", connector_id, workspace_id))
        return ("tool",)

    def disconnect(self, connector_id):
        self.calls.append(("disconnect", connector_id))

    def call(self, connector_id, *, workspace_id, name, arguments):
        self.calls.append(("call", connector_id, workspace_id, name, arguments))
        return {"ok": True}

    def forget_account(self, connector_id, *, credential_delete, profile_delete):
        self.calls.append(("forget", connector_id))
        credential_delete(f"dpapi://{connector_id}")
        profile_delete(connector_id)


def _service(tmp_path):
    registry = PluginRegistry()
    registry.install(
        PluginManifest(
            2,
            "notes",
            "1.0.0",
            "connector",
            "notes",
            "sidecar",
            ("text",),
            frozenset({"notes.read"}),
            "a" * 64,
            services=(
                PluginService(
                    "main", "stdio", "runtime/notes.exe", "b" * 64,
                    credential_env="NOTES_TOKEN",
                ),
            ),
        )
    )
    connectors = ConnectorRegistry(root=tmp_path / "connectors")
    credentials = FakeCredentials()
    host = FakeHost()
    profiles_deleted = []
    service = PluginConnectorService(
        plugin_registry=registry,
        connector_registry=connectors,
        runtime_host=host,
        credential_store=credentials,
        profile_delete=lambda connector_id: profiles_deleted.append(connector_id),
        id_factory=lambda: "pc-notes-001",
    )
    return service, connectors, credentials, host, profiles_deleted


def test_connector_service_requires_confirmation_and_never_accepts_command(tmp_path):
    service, *_ = _service(tmp_path)
    with pytest.raises(PluginConnectorError, match="确认"):
        service.create(
            plugin_name="notes",
            version="1.0.0",
            service_name="main",
            project_id="project-a",
            account_id="account-main",
            credential="secret",
            confirmed=False,
        )


def test_connector_service_creates_connects_lists_and_forgets_account(tmp_path):
    service, registry, credentials, host, profiles_deleted = _service(tmp_path)
    created = service.create(
        plugin_name="notes",
        version="1.0.0",
        service_name="main",
        project_id="project-a",
        account_id="account-main",
        credential="secret",
        confirmed=True,
    )
    connector_id = created["connector_id"]
    assert connector_id == "pc-notes-001"
    assert "credential_ref" not in created
    assert credentials.values[connector_id] == "secret"

    assert service.connect(connector_id, project_id="project-a")["tools"] == 1
    assert service.list(project_id="project-a")[0]["account_id"] == "account-main"
    service.disconnect(connector_id, project_id="project-a")
    service.forget(connector_id, project_id="project-a")

    assert host.calls[-1] == ("forget", connector_id)
    assert profiles_deleted == [connector_id]
    assert credentials.values == {}
    assert registry.get(connector_id).authorized is False


def test_connector_service_rejects_cross_project_operations(tmp_path):
    service, *_ = _service(tmp_path)
    created = service.create(
        plugin_name="notes",
        version="1.0.0",
        service_name="main",
        project_id="project-a",
        account_id="account-main",
        credential="secret",
        confirmed=True,
    )
    with pytest.raises(PluginConnectorError, match="项目"):
        service.connect(created["connector_id"], project_id="project-b")


def test_connector_service_calls_only_online_bound_account(tmp_path):
    service, registry, _, host, _ = _service(tmp_path)
    created = service.create(
        plugin_name="notes",
        version="1.0.0",
        service_name="main",
        project_id="project-a",
        account_id="account-main",
        credential="secret",
        confirmed=True,
    )
    with pytest.raises(PluginConnectorError, match="在线"):
        service.call_tool(
            plugin_name="notes",
            plugin_version="1.0.0",
            service_name="main",
            tool_name="publish",
            project_id="project-a",
            account_id="account-main",
            arguments={"title": "草稿"},
        )

    service.connect(created["connector_id"], project_id="project-a")
    registry.connect(created["connector_id"])
    result = service.call_tool(
        plugin_name="notes",
        plugin_version="1.0.0",
        service_name="main",
        tool_name="publish",
        project_id="project-a",
        account_id="account-main",
        arguments={"title": "草稿"},
    )

    assert result == {"ok": True}
    assert host.calls[-1] == (
        "call",
        "pc-notes-001",
        "project-a",
        "publish",
        {"title": "草稿"},
    )


def test_connector_service_disconnects_all_online_accounts_for_plugin_version(tmp_path):
    service, registry, *_rest = _service(tmp_path)
    created = service.create(
        plugin_name="notes",
        version="1.0.0",
        service_name="main",
        project_id="project-a",
        account_id="account-main",
        credential="secret",
        confirmed=True,
    )
    service.connect(created["connector_id"], project_id="project-a")
    registry.connect(created["connector_id"])

    assert service.disconnect_plugin("notes", "1.0.0") == 1
    assert registry.get(created["connector_id"]).connected is False
