"""受控 MCP Client：协议握手、分页目录、实时白名单与进程回收。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Mapping, Sequence
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx

from .plugin_registry import PluginManifest
from .plugin_tools import PluginTool, PluginToolError


class McpClientError(RuntimeError):
    """MCP 协议、目录或进程生命周期错误。"""


class McpTransport(Protocol):
    async def request(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]: ...
    async def notify(self, method: str, params: Mapping[str, Any]) -> None: ...
    async def close(self) -> None: ...


class ManagedMcpClient:
    """插件连接私有持有的 MCP 会话，不向 Agent 暴露服务地址。"""

    def __init__(
        self,
        transport: McpTransport,
        *,
        manifest: PluginManifest,
        service: str,
        tool_metadata: Mapping[str, Mapping[str, Any]],
        max_pages: int = 32,
        max_tools: int = 1_000,
        max_catalog_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        if min(max_pages, max_tools, max_catalog_bytes) <= 0:
            raise McpClientError("MCP 目录上限必须为正数")
        self._transport = transport
        self._manifest = manifest
        self._service = service
        self._metadata = {name: dict(value) for name, value in tool_metadata.items()}
        self._max_pages = max_pages
        self._max_tools = max_tools
        self._max_catalog_bytes = max_catalog_bytes
        self._connected = False
        self._tools: dict[str, PluginTool] = {}

    async def connect(self) -> None:
        if self._connected:
            raise McpClientError("MCP Client 不能重复连接")
        try:
            starter = getattr(self._transport, "start", None)
            if callable(starter):
                await starter()
            result = await self._transport.request(
                "initialize",
                {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "looklift", "version": "2"},
                },
            )
            version = result.get("protocolVersion")
            if not isinstance(version, str) or not version:
                raise McpClientError("MCP 服务未返回协议版本")
            await self._transport.notify("notifications/initialized", {})
            self._connected = True
        except Exception:
            try:
                await self._transport.close()
            except Exception:
                pass
            raise

    async def refresh_tools(self) -> tuple[PluginTool, ...]:
        self._require_connected()
        cursor: str | None = None
        tools: list[PluginTool] = []
        total_bytes = 0
        seen_cursors: set[str] = set()
        for _page in range(self._max_pages):
            params = {} if cursor is None else {"cursor": cursor}
            result = await self._transport.request("tools/list", params)
            raw_tools = result.get("tools")
            if not isinstance(raw_tools, list):
                raise McpClientError("MCP tools/list 返回格式无效")
            total_bytes += len(json.dumps(raw_tools, ensure_ascii=False).encode("utf-8"))
            if total_bytes > self._max_catalog_bytes or len(tools) + len(raw_tools) > self._max_tools:
                raise McpClientError("MCP 工具目录超过安全上限")
            for raw in raw_tools:
                tools.append(self._parse_tool(raw))
            next_cursor = result.get("nextCursor")
            if next_cursor is None:
                break
            if not isinstance(next_cursor, str) or not next_cursor or next_cursor in seen_cursors:
                raise McpClientError("MCP 工具目录游标无效")
            seen_cursors.add(next_cursor)
            cursor = next_cursor
        else:
            raise McpClientError("MCP 工具目录分页超过安全上限")
        if len({tool.name for tool in tools}) != len(tools):
            raise McpClientError("MCP 实时目录包含重复工具")
        self._tools = {tool.name: tool for tool in tools}
        return tuple(tools)

    async def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        self._require_connected()
        if name not in self._tools:
            raise McpClientError("工具不在最新 MCP 实时目录")
        result = await self._transport.request("tools/call", {"name": name, "arguments": dict(arguments)})
        if not isinstance(result, Mapping):
            raise McpClientError("MCP 工具结果无效")
        return dict(result)

    async def close(self) -> None:
        self._connected = False
        self._tools.clear()
        await self._transport.close()

    def _require_connected(self) -> None:
        if not self._connected:
            raise McpClientError("MCP Client 尚未连接")

    def _parse_tool(self, raw: Any) -> PluginTool:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("name"), str):
            raise McpClientError("MCP 工具声明无效")
        name = raw["name"]
        metadata = self._metadata.get(name)
        if metadata is None:
            raise McpClientError("MCP 返回了未经审核的未知工具")
        try:
            return PluginTool(
                plugin_name=self._manifest.name,
                plugin_version=self._manifest.version,
                plugin_hash=self._manifest.content_hash,
                service=self._service,
                name=name,
                description=str(raw.get("description", "")),
                input_schema=raw.get("inputSchema", {}),
                capabilities=frozenset(metadata.get("capabilities", ())),
                risk=str(metadata.get("risk", "")),
                aliases=tuple(metadata.get("aliases", ())),
                task_tags=tuple(metadata.get("task_tags", ())),
                requires_account=bool(metadata.get("requires_account", False)),
                confirmation_fields=tuple(metadata.get("confirmation_fields", ())),
            )
        except (TypeError, PluginToolError) as exc:
            raise McpClientError("MCP 工具 Schema 与审核元数据无效") from exc


class StdioMcpTransport:
    """不经过 Shell 的 stdio JSON-RPC 传输；一个连接串行配对请求。"""

    def __init__(
        self,
        command: Sequence[str],
        *,
        cwd: str | None = None,
        environment: Mapping[str, str] | None = None,
        timeout_seconds: float = 30,
        max_message_bytes: int = 1024 * 1024,
    ) -> None:
        if not command or timeout_seconds <= 0 or max_message_bytes <= 0:
            raise McpClientError("MCP stdio 启动配置无效")
        self._command = tuple(command)
        self._cwd = cwd
        self._environment = None if environment is None else dict(environment)
        self._timeout = timeout_seconds
        self._max_message_bytes = max_message_bytes
        self._process: asyncio.subprocess.Process | None = None
        self._next_id = 1
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._process is not None:
            raise McpClientError("MCP stdio 进程不能重复启动")
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self._command,
                cwd=self._cwd,
                env=self._environment,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                limit=self._max_message_bytes,
            )
        except OSError as exc:
            raise McpClientError("MCP stdio 进程启动失败") from exc

    async def request(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        async with self._lock:
            request_id = self._next_id
            self._next_id += 1
            await self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)})
            while True:
                message = await self._read()
                if message.get("id") != request_id:
                    if "id" in message:
                        raise McpClientError("MCP JSON-RPC 响应 ID 不匹配")
                    continue
                if "error" in message:
                    raise McpClientError("MCP 服务返回调用错误")
                result = message.get("result")
                if not isinstance(result, Mapping):
                    raise McpClientError("MCP JSON-RPC 缺少对象结果")
                return dict(result)

    async def notify(self, method: str, params: Mapping[str, Any]) -> None:
        async with self._lock:
            await self._write({"jsonrpc": "2.0", "method": method, "params": dict(params)})

    async def close(self) -> None:
        process = self._process
        self._process = None
        if process is None:
            return
        if process.stdin is not None:
            process.stdin.close()
        try:
            await asyncio.wait_for(process.wait(), timeout=0.5)
        except TimeoutError:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), timeout=0.5)
            except TimeoutError:
                process.kill()
                await process.wait()

    async def _write(self, message: Mapping[str, Any]) -> None:
        process = self._process
        if process is None or process.stdin is None:
            raise McpClientError("MCP stdio 进程尚未启动")
        encoded = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
        if len(encoded) > self._max_message_bytes:
            raise McpClientError("MCP JSON-RPC 请求过大")
        process.stdin.write(encoded)
        try:
            await asyncio.wait_for(process.stdin.drain(), timeout=self._timeout)
        except TimeoutError as exc:
            raise McpClientError("MCP stdio 写入超时") from exc

    async def _read(self) -> Mapping[str, Any]:
        process = self._process
        if process is None or process.stdout is None:
            raise McpClientError("MCP stdio 进程尚未启动")
        try:
            line = await asyncio.wait_for(process.stdout.readline(), timeout=self._timeout)
        except TimeoutError as exc:
            raise McpClientError("MCP stdio 响应超时") from exc
        if not line:
            raise McpClientError("MCP stdio 进程提前退出")
        if len(line) > self._max_message_bytes:
            raise McpClientError("MCP JSON-RPC 响应过大")
        try:
            message = json.loads(line)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise McpClientError("MCP JSON-RPC 响应不是有效 JSON") from exc
        if not isinstance(message, Mapping) or message.get("jsonrpc") != "2.0":
            raise McpClientError("MCP JSON-RPC 响应无效")
        return message


class StreamableHttpMcpTransport:
    """仅连接宿主管理回环端点的 MCP Streamable HTTP 传输。"""

    def __init__(
        self,
        endpoint: str,
        *,
        bearer_token: str,
        timeout_seconds: float = 30,
        max_response_bytes: int = 4 * 1024 * 1024,
        http_transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        parsed = urlparse(endpoint)
        if (
            parsed.scheme != "http"
            or parsed.hostname not in {"127.0.0.1", "::1"}
            or parsed.port is None
            or not parsed.path
        ):
            raise McpClientError("受管 MCP HTTP 端点必须是显式端口的回环地址")
        if not bearer_token or timeout_seconds <= 0 or max_response_bytes <= 0:
            raise McpClientError("MCP HTTP 认证或响应上限无效")
        self._endpoint = endpoint
        self._token = bearer_token
        self._max_response_bytes = max_response_bytes
        self._client = httpx.AsyncClient(
            transport=http_transport,
            timeout=timeout_seconds,
            follow_redirects=False,
            trust_env=False,
        )
        self._next_id = 1
        self._session_id: str | None = None
        self._protocol_version: str | None = None
        self._lock = asyncio.Lock()

    async def request(self, method: str, params: Mapping[str, Any]) -> Mapping[str, Any]:
        async with self._lock:
            request_id = self._next_id
            self._next_id += 1
            response = await self._post(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": dict(params)}
            )
            result = self._parse_response(response, request_id)
            if method == "initialize":
                version = result.get("protocolVersion")
                if isinstance(version, str) and version:
                    self._protocol_version = version
                session_id = response.headers.get("MCP-Session-Id")
                if session_id is not None:
                    if not session_id or any(ord(char) < 0x21 or ord(char) > 0x7E for char in session_id):
                        raise McpClientError("MCP HTTP Session ID 不安全")
                    self._session_id = session_id
            return result

    async def notify(self, method: str, params: Mapping[str, Any]) -> None:
        async with self._lock:
            response = await self._post(
                {"jsonrpc": "2.0", "method": method, "params": dict(params)}
            )
            if response.status_code != 202:
                raise McpClientError("MCP HTTP 通知未被服务端接受")

    async def close(self) -> None:
        try:
            if self._session_id is not None:
                response = await self._client.delete(
                    self._endpoint,
                    headers=self._headers(),
                )
                if response.status_code not in {200, 202, 204, 404, 405}:
                    raise McpClientError("MCP HTTP Session 关闭失败")
        finally:
            self._session_id = None
            await self._client.aclose()

    async def _post(self, message: Mapping[str, Any]) -> httpx.Response:
        try:
            request = self._client.build_request(
                "POST",
                self._endpoint,
                headers=self._headers(),
                json=dict(message),
            )
            response = await self._client.send(request, stream=True)
            try:
                if 300 <= response.status_code < 400:
                    raise McpClientError("MCP HTTP 禁止重定向")
                if response.status_code >= 400:
                    raise McpClientError("MCP HTTP 服务返回错误状态")
                chunks: list[bytes] = []
                size = 0
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > self._max_response_bytes:
                        raise McpClientError("MCP HTTP 响应超过安全上限")
                    chunks.append(chunk)
                return httpx.Response(
                    response.status_code,
                    headers=response.headers,
                    content=b"".join(chunks),
                    request=request,
                )
            finally:
                await response.aclose()
        except httpx.TimeoutException as exc:
            raise McpClientError("MCP HTTP 请求超时") from exc
        except httpx.HTTPError as exc:
            raise McpClientError("MCP HTTP 请求失败") from exc

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Authorization": f"Bearer {self._token}",
            "Origin": "http://127.0.0.1",
        }
        if self._session_id is not None:
            headers["MCP-Session-Id"] = self._session_id
        if self._protocol_version is not None:
            headers["MCP-Protocol-Version"] = self._protocol_version
        return headers

    def _parse_response(self, response: httpx.Response, request_id: int) -> dict[str, Any]:
        content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().casefold()
        if content_type == "application/json":
            try:
                message = response.json()
            except json.JSONDecodeError as exc:
                raise McpClientError("MCP HTTP JSON 响应无效") from exc
            return _jsonrpc_result(message, request_id)
        if content_type == "text/event-stream":
            try:
                text = response.content.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise McpClientError("MCP HTTP SSE 不是 UTF-8") from exc
            for block in text.replace("\r\n", "\n").split("\n\n"):
                data = "\n".join(
                    line[5:].lstrip()
                    for line in block.splitlines()
                    if line.startswith("data:")
                )
                if not data:
                    continue
                try:
                    message = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise McpClientError("MCP HTTP SSE data 无效") from exc
                if isinstance(message, Mapping) and message.get("id") == request_id:
                    return _jsonrpc_result(message, request_id)
            raise McpClientError("MCP HTTP SSE 未返回请求结果")
        raise McpClientError("MCP HTTP 响应 Content-Type 不受支持")


def _jsonrpc_result(message: Any, request_id: int) -> dict[str, Any]:
    if not isinstance(message, Mapping) or message.get("jsonrpc") != "2.0" or message.get("id") != request_id:
        raise McpClientError("MCP JSON-RPC 响应身份不匹配")
    if "error" in message:
        raise McpClientError("MCP 服务返回调用错误")
    result = message.get("result")
    if not isinstance(result, Mapping):
        raise McpClientError("MCP JSON-RPC 缺少对象结果")
    return dict(result)
