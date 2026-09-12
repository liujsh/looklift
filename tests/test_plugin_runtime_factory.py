from __future__ import annotations

import hashlib

import pytest

from looklift.connector import ConnectorManifest
from looklift.connector_registry import ConnectorConfig
from looklift.plugin_registry import PluginManifest, PluginRegistry, PluginService
from looklift.plugin_runtime import (
    PluginProfileStore,
    PluginRuntimeError,
    StdioPluginClientFactory,
)
from looklift.plugin_tools import PluginTool


class CapturingTransport:
    def __init__(self, command, cwd, environment):
        self.command = command
        self.cwd = cwd
        self.environment = environment

    async def request(self, _method, _params):
        return {}

    async def notify(self, _method, _params):
        return None

    async def close(self):
        return None


def _runtime_fixture(tmp_path):
    executable = tmp_path / "plugins" / "notes" / "1.0.0" / "runtime" / "notes.exe"
    executable.parent.mkdir(parents=True)
    executable.write_bytes(b"reviewed-runtime")
    digest = hashlib.sha256(executable.read_bytes()).hexdigest()
    service = PluginService(
        name="main",
        transport="stdio",
        entrypoint="runtime/notes.exe",
        entrypoint_sha256=digest,
        arguments=("--mcp",),
        credential_env="NOTES_TOKEN",
    )
    manifest = PluginManifest(
        2,
        "notes",
        "1.0.0",
        "connector",
        "notes",
        "sidecar",
        ("text",),
        frozenset({"notes.read"}),
        "a" * 64,
        services=(service,),
    )
    tool = PluginTool(
        "notes",
        "1.0.0",
        "a" * 64,
        "main",
        "list_notes",
        "读取笔记",
        {"type": "object"},
        frozenset({"notes.read"}),
        "external_read",
    )
    registry = PluginRegistry()
    registry.install(manifest, tools=(tool,))
    config = ConnectorConfig(
        ConnectorManifest("notes-main", "mcp", "notes.example", frozenset({"notes.read"})),
        credential_ref="dpapi://notes-main",
        workspace_id="project-a",
        account_id="account-main",
        authorized=True,
        plugin_name="notes",
        plugin_version="1.0.0",
        service="main",
    )
    return registry, config, executable


def test_stdio_factory_binds_reviewed_entrypoint_profile_and_credential(tmp_path):
    registry, config, executable = _runtime_fixture(tmp_path)
    captured = []

    def build(command, cwd, environment):
        transport = CapturingTransport(command, cwd, environment)
        captured.append(transport)
        return transport

    factory = StdioPluginClientFactory(
        install_root=tmp_path,
        registry=registry,
        credential_resolver=lambda reference: "secret-value" if reference == "dpapi://notes-main" else None,
        transport_builder=build,
        base_environment={"SYSTEMROOT": "C:\\Windows", "LEAK_ME": "no"},
    )

    factory(config)

    transport = captured[0]
    assert transport.command == (str(executable.resolve()), "--mcp")
    assert transport.environment["NOTES_TOKEN"] == "secret-value"
    assert transport.environment["LOOKLIFT_PLUGIN_PROFILE"].endswith("plugin-state\\notes-main")
    assert transport.environment["SYSTEMROOT"] == "C:\\Windows"
    assert "LEAK_ME" not in transport.environment


def test_stdio_factory_rejects_tampered_entrypoint(tmp_path):
    registry, config, executable = _runtime_fixture(tmp_path)
    executable.write_bytes(b"tampered")
    factory = StdioPluginClientFactory(
        install_root=tmp_path,
        registry=registry,
        credential_resolver=lambda _reference: "secret-value",
    )

    with pytest.raises(PluginRuntimeError, match="摘要"):
        factory(config)


def test_stdio_factory_requires_complete_plugin_binding(tmp_path):
    registry, config, _executable = _runtime_fixture(tmp_path)
    unbound = ConnectorConfig(
        config.manifest,
        credential_ref="dpapi://notes-main",
        authorized=True,
    )
    factory = StdioPluginClientFactory(
        install_root=tmp_path,
        registry=registry,
        credential_resolver=lambda _reference: "secret-value",
    )

    with pytest.raises(PluginRuntimeError, match="绑定"):
        factory(unbound)


def test_profile_store_only_removes_exact_connection_directory(tmp_path):
    profiles = PluginProfileStore(tmp_path)
    profile = profiles.prepare("notes-main")
    (profile / "cookie.db").write_bytes(b"secret")

    profiles.delete("notes-main")

    assert not profile.exists()
    with pytest.raises(PluginRuntimeError, match="ID"):
        profiles.delete("../outside")
