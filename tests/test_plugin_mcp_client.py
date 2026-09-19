from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from looklift.plugin_mcp_client import (
    McpClientError,
    ManagedMcpClient,
    StreamableHttpMcpTransport,
)
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


class StartAwareTransport(FakeTransport):
    def __init__(self, pages):
        super().__init__(pages)
        self.started = False

    async def start(self):
        self.started = True

    async def request(self, method, params):
        assert self.started is True
        return await super().request(method, params)


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


def test_mcp_client_starts_transport_before_initialize():
    transport = StartAwareTransport({None: {"tools": []}})
    client = ManagedMcpClient(
        transport,
        manifest=_manifest(),
        service="main",
        tool_metadata={},
    )

    asyncio.run(client.connect())

    assert transport.started is True
    asyncio.run(client.close())


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


def test_streamable_http_transport_keeps_auth_origin_protocol_and_session_headers():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "DELETE":
            return httpx.Response(204)
        payload = json.loads(request.content)
        if "id" not in payload:
            return httpx.Response(202)
        headers = {"Content-Type": "application/json"}
        if payload["method"] == "initialize":
            headers["MCP-Session-Id"] = "secure-session"
            result = {"protocolVersion": "2025-11-25"}
        else:
            assert request.headers["MCP-Session-Id"] == "secure-session"
            assert request.headers["MCP-Protocol-Version"] == "2025-11-25"
            result = {"tools": []}
        assert request.headers["Authorization"] == "Bearer local-secret"
        assert request.headers["Origin"] == "http://127.0.0.1"
        return httpx.Response(200, headers=headers, json={"jsonrpc": "2.0", "id": payload["id"], "result": result})

    transport = StreamableHttpMcpTransport(
        "http://127.0.0.1:43123/mcp",
        bearer_token="local-secret",
        http_transport=httpx.MockTransport(handler),
    )

    async def exercise():
        initialized = await transport.request("initialize", {})
        assert initialized["protocolVersion"] == "2025-11-25"
        await transport.notify("notifications/initialized", {})
        assert await transport.request("tools/list", {}) == {"tools": []}
        await transport.close()

    asyncio.run(exercise())
    assert seen[-1].method == "DELETE"


def test_streamable_http_transport_accepts_sse_response_and_rejects_remote_url():
    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        body = f"event: message\ndata: {json.dumps({'jsonrpc': '2.0', 'id': payload['id'], 'result': {'ok': True}})}\n\n"
        return httpx.Response(200, headers={"Content-Type": "text/event-stream"}, text=body)

    transport = StreamableHttpMcpTransport(
        "http://[::1]:43123/mcp",
        bearer_token="local-secret",
        http_transport=httpx.MockTransport(handler),
    )
    assert asyncio.run(transport.request("ping", {})) == {"ok": True}
    asyncio.run(transport.close())

    with pytest.raises(McpClientError, match="回环"):
        StreamableHttpMcpTransport("https://example.com/mcp", bearer_token="secret")


def test_streamable_http_transport_resumes_closed_sse_with_last_event_id():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "DELETE":
            return httpx.Response(204)
        if request.method == "POST":
            body = "id: stream-1\nretry: 0\ndata:\n\n"
            return httpx.Response(
                200,
                headers={
                    "Content-Type": "text/event-stream",
                    "MCP-Session-Id": "resume-session",
                },
                text=body,
            )
        assert request.method == "GET"
        assert request.headers["Last-Event-ID"] == "stream-1"
        assert request.headers["MCP-Session-Id"] == "resume-session"
        body = (
            "id: stream-2\nevent: message\ndata: "
            + json.dumps(
                {"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}
            )
            + "\n\n"
        )
        return httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, text=body
        )

    transport = StreamableHttpMcpTransport(
        "http://127.0.0.1:43123/mcp",
        bearer_token="local-secret",
        http_transport=httpx.MockTransport(handler),
    )

    assert asyncio.run(transport.request("initialize", {})) == {"ok": True}
    assert [request.method for request in seen] == ["POST", "GET"]
    asyncio.run(transport.close())


def test_streamable_http_transport_limits_resume_attempts_and_event_id():
    def endless_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text="id: cursor\nretry: 0\ndata:\n\n",
        )

    transport = StreamableHttpMcpTransport(
        "http://127.0.0.1:43123/mcp",
        bearer_token="local-secret",
        max_resume_attempts=2,
        http_transport=httpx.MockTransport(endless_handler),
    )
    with pytest.raises(McpClientError, match="重连上限"):
        asyncio.run(transport.request("ping", {}))
    asyncio.run(transport.close())

    def unsafe_handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/event-stream"},
            text="id: unsafe\u0000cursor\ndata:\n\n",
        )

    unsafe = StreamableHttpMcpTransport(
        "http://127.0.0.1:43123/mcp",
        bearer_token="local-secret",
        http_transport=httpx.MockTransport(unsafe_handler),
    )
    with pytest.raises(McpClientError, match="事件 ID"):
        asyncio.run(unsafe.request("ping", {}))
    asyncio.run(unsafe.close())


def test_streamable_http_transport_explicitly_rejects_server_requests():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen.append(payload)
        if "method" not in payload:
            assert payload == {
                "jsonrpc": "2.0",
                "id": "server-1",
                "error": {
                    "code": -32601,
                    "message": "客户端未启用 MCP 服务端反向请求",
                },
            }
            return httpx.Response(202)
        body = (
            "event: message\ndata: "
            + json.dumps(
                {
                    "jsonrpc": "2.0",
                    "id": "server-1",
                    "method": "sampling/createMessage",
                    "params": {},
                }
            )
            + "\n\nevent: message\ndata: "
            + json.dumps(
                {"jsonrpc": "2.0", "id": payload["id"], "result": {"ok": True}}
            )
            + "\n\n"
        )
        return httpx.Response(
            200, headers={"Content-Type": "text/event-stream"}, text=body
        )

    transport = StreamableHttpMcpTransport(
        "http://127.0.0.1:43123/mcp",
        bearer_token="local-secret",
        http_transport=httpx.MockTransport(handler),
    )

    assert asyncio.run(transport.request("ping", {})) == {"ok": True}
    assert len(seen) == 2
    asyncio.run(transport.close())


def test_streamable_http_transport_stops_reading_when_response_exceeds_limit():
    class OversizedStream(httpx.AsyncByteStream):
        def __init__(self):
            self.reads = 0

        async def __aiter__(self):
            for _ in range(3):
                self.reads += 1
                yield b"x" * 8

    stream = OversizedStream()

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "application/json"},
            stream=stream,
        )

    transport = StreamableHttpMcpTransport(
        "http://127.0.0.1:43123/mcp",
        bearer_token="local-secret",
        max_response_bytes=10,
        http_transport=httpx.MockTransport(handler),
    )

    with pytest.raises(McpClientError, match="安全上限"):
        asyncio.run(transport.request("ping", {}))
    assert stream.reads == 2
    asyncio.run(transport.close())
