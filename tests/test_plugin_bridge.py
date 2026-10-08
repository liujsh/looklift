from __future__ import annotations

import json
from urllib.request import Request, urlopen

from looklift.capabilities import CapabilityGrant
from looklift.plugin_bridge import (
    PluginBridgeSession,
    ScopedPluginBridgeGateway,
    bridge_tool_definitions,
    native_tool_definitions,
)
from looklift.plugin_registry import PluginManifest, PluginRegistry
from looklift.plugin_tools import PluginTool, PluginToolCatalog, PluginToolGateway
from looklift.scoped_tool_http import ScopedToolHttpServer


def _session():
    digest = "a" * 64
    registry = PluginRegistry()
    tool = PluginTool(
        "notes", "1.0.0", digest, "main", "list_notes", "读取笔记",
        {"type": "object", "properties": {"limit": {"type": "integer", "minimum": 1}}},
        frozenset({"notes.read"}), "read_only", aliases=("找笔记",),
    )
    registry.install(
        PluginManifest(
            2, "notes", "1.0.0", "connector", "notes", "sidecar", ("text",),
            frozenset({"notes.read"}), digest, aliases=("笔记",),
        ),
        tools=(tool,),
    )
    catalog = PluginToolCatalog(registry)
    gateway = PluginToolGateway(catalog, lambda selected, args: {"ok": True, "name": selected.name, "limit": args.get("limit")})
    grant = CapabilityGrant("notes", frozenset({"notes.read"}), "project-a", digest)
    return PluginBridgeSession(
        catalog=catalog,
        gateway=gateway,
        project_id="project-a",
        grants=(grant,),
        resource_reader=lambda ref, offset, limit: {"ref": ref, "offset": offset, "text": "内容"[:limit]},
    )


def test_bridge_requires_discovery_activation_before_invoke():
    session = _session()
    found = session.call("discover_tools", {"query": "找笔记"})
    identity = found["tools"][0]["identity"]

    denied = session.call("invoke_tool", {"identity": identity, "schema_hash": "0" * 64, "arguments": {"limit": 1}})
    assert denied["ok"] is False
    assert denied["error"]["code"] == "tool_not_activated"

    described = session.call("describe_tools", {"identities": [identity]})
    tool = described["tools"][0]
    result = session.call(
        "invoke_tool",
        {"identity": identity, "schema_hash": tool["schema_hash"], "arguments": {"limit": 2}},
    )
    assert result == {"ok": True, "name": "list_notes", "limit": 2}
    assert native_tool_definitions(session.active_tools)[0]["name"] == tool["provider_name"]


def test_bridge_does_not_inherit_gateway_activation_from_another_session():
    session = _session()
    found = session.call("discover_tools", {"query": "找笔记"})
    identity = found["tools"][0]["identity"]
    activated = session._gateway.activate(  # noqa: SLF001 - 模拟共享 Gateway 被另一会话激活
        [identity],
        project_id="project-a",
        grants=session._grants,  # noqa: SLF001
    )

    denied = session.call(
        "invoke_tool",
        {
            "identity": identity,
            "schema_hash": activated.tools[0].schema_hash,
            "arguments": {"limit": 1},
        },
    )

    assert denied["ok"] is False
    assert denied["error"]["code"] == "tool_not_activated"


def test_bridge_uses_existing_scoped_localhost_transport():
    gateway = ScopedPluginBridgeGateway()
    grant = gateway.bind(_session())
    server = ScopedToolHttpServer(gateway)
    server.start()
    try:
        body = json.dumps({"query": "笔记"}).encode()
        request = Request(
            f"{server.url}/tools/discover_tools",
            data=body,
            headers={"Authorization": f"Bearer {grant.token}", "Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(request, timeout=2) as response:
            payload = json.loads(response.read())
        assert payload["result"]["tools"][0]["plugin_name"] == "notes"
    finally:
        server.close()


def test_bridge_definitions_are_fixed_and_platform_neutral():
    definitions = bridge_tool_definitions()
    assert [item["name"] for item in definitions] == [
        "discover_tools", "describe_tools", "invoke_tool", "read_plugin_resource"
    ]
    assert all(item["inputSchema"]["type"] == "object" for item in definitions)
