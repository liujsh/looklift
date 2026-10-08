"""API 动态工具与 CLI 固定桥接共用的 Plugin 会话。"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .capabilities import CapabilityGrant
from .plugin_tools import (
    ActiveToolSet,
    ExposureBudget,
    PluginToolCatalog,
    PluginToolError,
    PluginToolGateway,
)
from .scoped_tool_gateway import GatewayToolResult, ScopedToolGrant


_BRIDGE_NAMES = frozenset(
    {"discover_tools", "describe_tools", "invoke_tool", "read_plugin_resource"}
)


def bridge_tool_definitions() -> tuple[dict[str, Any], ...]:
    """CLI 固定暴露的有界桥接工具，不包含任何平台专属名称。"""
    return (
        {
            "name": "discover_tools",
            "description": "按当前项目权限搜索已安装插件工具，只返回短摘要。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "minLength": 1},
                    "plugin_name": {"type": "string"},
                    "cursor": {"type": ["string", "null"]},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "describe_tools",
            "description": "加载已发现工具的完整 Schema 并创建活动工具集。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "identities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 16,
                        "uniqueItems": True,
                    }
                },
                "required": ["identities"],
                "additionalProperties": False,
            },
        },
        {
            "name": "invoke_tool",
            "description": "调用已激活工具；宿主重新校验 Schema、权限与确认边界。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "identity": {"type": "string"},
                    "schema_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    "arguments": {"type": "object"},
                },
                "required": ["identity", "schema_hash", "arguments"],
                "additionalProperties": False,
            },
        },
        {
            "name": "read_plugin_resource",
            "description": "读取插件声明的受控 Skill 或 Reference 片段。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "ref": {"type": "string", "minLength": 1},
                    "offset": {"type": "integer", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 16000},
                },
                "required": ["ref"],
                "additionalProperties": False,
            },
        },
    )


def native_tool_definitions(active: ActiveToolSet | None) -> tuple[dict[str, Any], ...]:
    """把活动工具完整、无损地投影为传输无关 Provider 定义。"""
    if active is None:
        return ()
    return tuple(
        {
            "name": tool.provider_name,
            "description": tool.description,
            "inputSchema": dict(tool.input_schema),
        }
        for tool in active.tools
    )


ResourceReader = Callable[[str, int, int], Mapping[str, Any]]


class PluginBridgeSession:
    """一次 Plugin Attempt 的发现预算、活动集与调用映射。"""

    def __init__(
        self,
        *,
        catalog: PluginToolCatalog,
        gateway: PluginToolGateway,
        project_id: str,
        grants: Sequence[CapabilityGrant],
        resource_reader: ResourceReader | None = None,
        exposure_budget: ExposureBudget = ExposureBudget(),
        discovery_limit: int = 10,
        account_id: str | None = None,
        asset_hashes: tuple[str, ...] = (),
    ) -> None:
        self._catalog = catalog
        self._gateway = gateway
        self._project_id = project_id
        self._grants = tuple(grants)
        self._resource_reader = resource_reader
        self._budget = exposure_budget
        self._discovery_limit = discovery_limit
        self._account_id = account_id
        self._asset_hashes = asset_hashes
        self._active: ActiveToolSet | None = None

    @property
    def active_tools(self) -> ActiveToolSet | None:
        return self._active

    def call(self, name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if name not in _BRIDGE_NAMES:
            return _error("bridge_tool_unknown", "桥接工具不受支持")
        try:
            if name == "discover_tools":
                return self._discover(arguments)
            if name == "describe_tools":
                return self._describe(arguments)
            if name == "invoke_tool":
                return self._invoke(arguments)
            return self._read_resource(arguments)
        except (KeyError, TypeError, ValueError, PluginToolError):
            code = "tool_not_activated" if name == "invoke_tool" and self._active is None else "invalid_arguments"
            return _error(code, "桥接调用未通过宿主校验")

    def call_native(self, provider_name: str, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if self._active is None:
            return _error("tool_not_activated", "尚未创建活动工具集")
        selected = next(
            (tool for tool in self._active.tools if tool.provider_name == provider_name),
            None,
        )
        if selected is None:
            return _error("tool_not_activated", "Provider 工具不在当前活动集")
        try:
            return self._gateway.invoke(selected.identity, selected.schema_hash, arguments)
        except PluginToolError:
            return _error("tool_call_rejected", "动态工具调用未通过宿主校验")

    def _discover(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        page = self._catalog.discover(
            arguments["query"],
            project_id=self._project_id,
            grants=self._grants,
            limit=arguments.get("limit", self._discovery_limit),
            cursor=arguments.get("cursor"),
            plugin_name=arguments.get("plugin_name"),
        )
        return {
            "ok": True,
            "tools": [tool.public_dict() for tool in page.items],
            "next_cursor": page.next_cursor,
        }

    def _describe(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        identities = arguments["identities"]
        self._active = self._gateway.activate(
            identities,
            project_id=self._project_id,
            grants=self._grants,
            budget=self._budget,
            account_id=self._account_id,
            asset_hashes=self._asset_hashes,
        )
        return {
            "ok": True,
            "revision": self._active.revision,
            "schema_bytes": self._active.schema_bytes,
            "tools": [
                {
                    "identity": tool.identity,
                    "provider_name": tool.provider_name,
                    "schema_hash": tool.schema_hash,
                    "description": tool.description,
                    "input_schema": dict(tool.input_schema),
                }
                for tool in self._active.tools
            ],
        }

    def _invoke(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        identity = arguments["identity"]
        schema_hash = arguments["schema_hash"]
        if self._active is None or not any(
            tool.identity == identity and tool.schema_hash == schema_hash
            for tool in self._active.tools
        ):
            return _error("tool_not_activated", "工具不在当前会话的活动集")
        return self._gateway.invoke(
            identity, schema_hash, arguments["arguments"]
        )

    def _read_resource(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        if self._resource_reader is None:
            return _error("resource_unavailable", "当前插件任务没有可读取资源")
        result = self._resource_reader(
            arguments["ref"], arguments.get("offset", 0), arguments.get("limit", 4000)
        )
        return {"ok": True, **dict(result)}


@dataclass
class _BridgeGrant:
    session: PluginBridgeSession
    expires_at: float
    revoked: bool = False


class ScopedPluginBridgeGateway:
    """让 Pi Extension 通过现有 localhost HTTP 访问单次桥接会话。"""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._grants: dict[str, _BridgeGrant] = {}
        self._lock = threading.RLock()

    @property
    def allowed_tools(self) -> frozenset[str]:
        return _BRIDGE_NAMES

    def bind(self, session: PluginBridgeSession, *, ttl_seconds: float = 300) -> ScopedToolGrant:
        if ttl_seconds <= 0:
            raise ValueError("桥接 Token 有效期必须为正数")
        token = secrets.token_urlsafe(32)
        expires_at = self._clock() + ttl_seconds
        with self._lock:
            self._grants[token] = _BridgeGrant(session, expires_at)
        return ScopedToolGrant(token, expires_at)

    def revoke(self, token: str) -> None:
        with self._lock:
            grant = self._grants.get(token)
            if grant is not None:
                grant.revoked = True

    def call(self, token: str, tool_name: str, arguments: Mapping[str, Any]) -> GatewayToolResult:
        with self._lock:
            grant = self._grants.get(token)
            if grant is None:
                return GatewayToolResult(_error("token_invalid", "桥接 Token 无效"))
            if grant.revoked:
                return GatewayToolResult(_error("token_revoked", "桥接 Token 已撤销"))
            if self._clock() >= grant.expires_at:
                grant.revoked = True
                return GatewayToolResult(_error("token_expired", "桥接 Token 已过期"))
        return GatewayToolResult(grant.session.call(tool_name, arguments))


def _error(code: str, message: str) -> dict[str, Any]:
    return {"ok": False, "error": {"code": code, "message": message}}
