from __future__ import annotations

import asyncio

import pytest

from looklift.plugin_mcp_client import McpClientError, ManagedMcpClient
from looklift.plugin_registry import PluginManifest


def _manifest() -> PluginManifest:
    return PluginManifest(
        2,
        "redbook",
        "1.0.0",
        "connector",
        "social_publish",
        "sidecar",
        ("exported_assets",),
        frozenset({"social.publish"}),
        "a" * 64,
    )


class FakeTransport:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []
        self.closed = False

    async def request(self, method, params):
        self.calls.append((method, params))
        if method == "initialize":
            return {"protocolVersion": "2025-11-25", "serverInfo": {"name": "fake", "version": "1"}}
        if method == "tools/list":
            return self.pages[params.get("cursor")]
        if method == "tools/call":
            return {"content": [{"type": "text", "text": "ok"}], "isError": False}
        raise AssertionError(method)

    async def notify(self, method, params):
        self.calls.append((method, params))

    async def close(self):
        self.closed = True


def test_mcp_client_negotiates_and_collects_paginated_catalog():
    transport = FakeTransport(
        {
            None: {
                "tools": [{"name": "status", "description": "检查状态", "inputSchema": {"type": "object"}}],
                "nextCursor": "page-2",
            },
            "page-2": {
                "tools": [{"name": "publish", "description": "发布", "inputSchema": {"type": "object"}}]
            },
        }
    )
    client = ManagedMcpClient(
        transport,
        manifest=_manifest(),
        service="main",
        tool_metadata={
            "status": {"capabilities": ["social.publish"], "risk": "external_read"},
            "publish": {"capabilities": ["social.publish"], "risk": "external_write"},
        },
    )

    async def exercise():
        await client.connect()
        tools = await client.refresh_tools()
        result = await client.call("publish", {})
        await client.close()
        return tools, result

    tools, result = asyncio.run(exercise())
    assert [tool.name for tool in tools] == ["status", "publish"]
    assert result["isError"] is False
    assert transport.calls[1][0] == "notifications/initialized"
    assert transport.closed is True


def test_mcp_client_rejects_unreviewed_or_oversized_catalog():
    transport = FakeTransport(
        {None: {"tools": [{"name": "surprise", "inputSchema": {"type": "object"}}]}}
    )
    client = ManagedMcpClient(
        transport,
        manifest=_manifest(),
        service="main",
        tool_metadata={},
        max_tools=1,
    )

    async def exercise():
        await client.connect()
        await client.refresh_tools()

    with pytest.raises(McpClientError, match="审核"):
        asyncio.run(exercise())


def test_mcp_client_never_calls_tool_missing_from_latest_catalog():
    transport = FakeTransport({None: {"tools": []}})
    client = ManagedMcpClient(
        transport,
        manifest=_manifest(),
        service="main",
        tool_metadata={},
    )

    async def exercise():
        await client.connect()
        await client.refresh_tools()
        await client.call("publish", {})

    with pytest.raises(McpClientError, match="实时目录"):
        asyncio.run(exercise())
