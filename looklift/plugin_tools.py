"""Plugin MCP 工具目录、渐进暴露与统一执行守卫。"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

from .capabilities import CapabilityGrant
from .plugin_actions import ActionState, PluginActionStore
from .plugin_registry import PluginRegistry


_SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_RISKS = frozenset({"read_only", "local_write", "external_read", "external_write"})


class PluginToolError(ValueError):
    """工具目录、暴露或执行违反宿主契约。"""


def _canonical_hash(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PluginTool:
    plugin_name: str
    plugin_version: str
    plugin_hash: str
    service: str
    name: str
    description: str
    input_schema: Mapping[str, Any]
    capabilities: frozenset[str]
    risk: str
    aliases: tuple[str, ...] = ()
    task_tags: tuple[str, ...] = ()
    requires_account: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "capabilities", frozenset(self.capabilities))
        object.__setattr__(self, "aliases", tuple(self.aliases))
        object.__setattr__(self, "task_tags", tuple(self.task_tags))
        if not all(_SAFE_NAME.fullmatch(value) for value in (self.plugin_name, self.service, self.name)):
            raise PluginToolError("Plugin、服务或工具名称不安全")
        if not re.fullmatch(r"[0-9a-f]{64}", self.plugin_hash):
            raise PluginToolError("Plugin 工具缺少有效版本摘要")
        if self.risk not in _RISKS:
            raise PluginToolError("工具风险分类不受支持")
        if not isinstance(self.input_schema, Mapping) or self.input_schema.get("type") != "object":
            raise PluginToolError("工具输入 Schema 顶层必须是 object")
        _validate_schema_shape(self.input_schema)
        object.__setattr__(self, "input_schema", dict(self.input_schema))

    @property
    def identity(self) -> str:
        return f"{self.plugin_name}@{self.plugin_version}/{self.service}/{self.name}"

    @property
    def schema_hash(self) -> str:
        return _canonical_hash(self.input_schema)

    def as_storage_dict(self) -> dict[str, Any]:
        return {
            "plugin_name": self.plugin_name,
            "plugin_version": self.plugin_version,
            "plugin_hash": self.plugin_hash,
            "service": self.service,
            "name": self.name,
            "description": self.description,
            "input_schema": dict(self.input_schema),
            "capabilities": sorted(self.capabilities),
            "risk": self.risk,
            "aliases": list(self.aliases),
            "task_tags": list(self.task_tags),
            "requires_account": self.requires_account,
        }

    @classmethod
    def from_storage_dict(cls, value: Mapping[str, Any]) -> "PluginTool":
        raw = dict(value)
        raw["capabilities"] = frozenset(raw.get("capabilities", ()))
        raw["aliases"] = tuple(raw.get("aliases", ()))
        raw["task_tags"] = tuple(raw.get("task_tags", ()))
        return cls(**raw)


@dataclass(frozen=True)
class DiscoveredTool:
    identity: str
    plugin_name: str
    name: str
    description: str
    risk: str
    state: str = "discoverable"

    def public_dict(self) -> dict[str, str]:
        return {
            "identity": self.identity,
            "plugin_name": self.plugin_name,
            "name": self.name,
            "description": self.description,
            "risk": self.risk,
            "state": self.state,
        }


@dataclass(frozen=True)
class DiscoveryPage:
    items: tuple[DiscoveredTool, ...]
    next_cursor: str | None = None


@dataclass(frozen=True)
class ExposureBudget:
    max_schema_bytes: int = 32 * 1024
    max_tools: int = 16

    def __post_init__(self) -> None:
        if self.max_schema_bytes <= 0 or self.max_tools <= 0:
            raise PluginToolError("暴露预算必须为正数")


@dataclass(frozen=True)
class ActiveTool:
    identity: str
    provider_name: str
    schema_hash: str
    description: str
    input_schema: Mapping[str, Any]


@dataclass(frozen=True)
class ActiveToolSet:
    revision: str
    tools: tuple[ActiveTool, ...]
    schema_bytes: int


class PluginToolCatalog:
    """在本地全目录之上提供权限过滤后的召回与完整 Schema 激活。"""

    def __init__(self, registry: PluginRegistry) -> None:
        self._registry = registry

    def discover(
        self,
        query: str,
        *,
        project_id: str,
        grants: Sequence[CapabilityGrant],
        limit: int = 10,
        cursor: str | None = None,
        plugin_name: str | None = None,
    ) -> DiscoveryPage:
        if not isinstance(query, str) or not query.strip():
            raise PluginToolError("发现查询不能为空")
        if limit < 1 or limit > 100:
            raise PluginToolError("发现分页大小无效")
        try:
            offset = int(cursor or "0")
        except ValueError as exc:
            raise PluginToolError("发现游标无效") from exc
        if offset < 0:
            raise PluginToolError("发现游标无效")
        authorized = {
            (grant.subject, grant.version_hash): grant
            for grant in grants
            if grant.project_id == project_id and grant.active()
        }
        terms = _terms(query)
        ranked: list[tuple[int, PluginTool]] = []
        for tool in self._registry.all_tools():
            if plugin_name is not None and tool.plugin_name != plugin_name:
                continue
            grant = authorized.get((tool.plugin_name, tool.plugin_hash))
            if grant is None or not tool.capabilities <= grant.capabilities:
                continue
            manifest = self._registry.resolve(tool.plugin_name, tool.plugin_version)
            score = _score(terms, tool, manifest.aliases)
            if score > 0:
                ranked.append((score, tool))
        ranked.sort(key=lambda value: (-value[0], value[1].identity))
        selected = ranked[offset : offset + limit]
        next_offset = offset + len(selected)
        next_cursor = str(next_offset) if next_offset < len(ranked) else None
        return DiscoveryPage(
            tuple(
                DiscoveredTool(tool.identity, tool.plugin_name, tool.name, tool.description, tool.risk)
                for _, tool in selected
            ),
            next_cursor,
        )

    def activate(
        self,
        identities: Iterable[str],
        *,
        budget: ExposureBudget = ExposureBudget(),
    ) -> ActiveToolSet:
        requested = tuple(dict.fromkeys(identities))
        if len(requested) > budget.max_tools:
            raise PluginToolError("工具数量超过活动集预算")
        by_identity = {tool.identity: tool for tool in self._registry.all_tools()}
        try:
            tools = tuple(by_identity[identity] for identity in requested)
        except KeyError as exc:
            raise PluginToolError("工具身份已失效") from exc
        schema_bytes = sum(
            len(json.dumps(tool.input_schema, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            for tool in tools
        )
        if schema_bytes > budget.max_schema_bytes:
            raise PluginToolError("完整 Schema 超过活动集预算，不能截断")
        active = tuple(
            ActiveTool(
                identity=tool.identity,
                provider_name=_provider_name(tool),
                schema_hash=tool.schema_hash,
                description=tool.description,
                input_schema=dict(tool.input_schema),
            )
            for tool in tools
        )
        revision = _canonical_hash(
            {"tools": [{"identity": item.identity, "schema_hash": item.schema_hash} for item in active]}
        )
        return ActiveToolSet(revision, active, schema_bytes)

    def resolve(self, identity: str) -> PluginTool:
        for tool in self._registry.all_tools():
            if tool.identity == identity:
                return tool
        raise PluginToolError("工具身份已失效")


class PluginToolGateway:
    """动态工具和桥接工具共用的服务端执行守卫。"""

    def __init__(
        self,
        catalog: PluginToolCatalog,
        executor: Callable[[PluginTool, dict[str, Any]], Mapping[str, Any]],
        *,
        action_store: PluginActionStore | None = None,
    ) -> None:
        self._catalog = catalog
        self._executor = executor
        self._action_store = action_store
        self._active: dict[str, str] = {}
        self._project_id: str | None = None
        self._account_id: str | None = None
        self._asset_hashes: tuple[str, ...] = ()

    def activate(
        self,
        identities: Iterable[str],
        *,
        project_id: str,
        grants: Sequence[CapabilityGrant],
        budget: ExposureBudget = ExposureBudget(),
        account_id: str | None = None,
        asset_hashes: tuple[str, ...] = (),
    ) -> ActiveToolSet:
        authorized: list[str] = []
        for identity in identities:
            tool = self._catalog.resolve(identity)
            if not any(
                grant.subject == tool.plugin_name
                and grant.project_id == project_id
                and grant.version_hash == tool.plugin_hash
                and grant.active()
                and tool.capabilities <= grant.capabilities
                for grant in grants
            ):
                raise PluginToolError("工具未获得当前项目授权")
            authorized.append(identity)
        active = self._catalog.activate(authorized, budget=budget)
        self._active = {tool.identity: tool.schema_hash for tool in active.tools}
        self._project_id = project_id
        self._account_id = account_id
        self._asset_hashes = tuple(asset_hashes)
        return active

    def invoke(
        self,
        identity: str,
        schema_hash: str,
        arguments: Mapping[str, Any],
    ) -> dict[str, Any]:
        activated_hash = self._active.get(identity)
        if activated_hash is None:
            raise PluginToolError("工具尚未激活")
        tool = self._catalog.resolve(identity)
        if activated_hash != tool.schema_hash:
            self._active.pop(identity, None)
            raise PluginToolError("工具目录变化，活动工具已失效")
        if schema_hash != activated_hash:
            raise PluginToolError("Schema Hash 不匹配")
        try:
            _validate_instance(arguments, tool.input_schema)
        except ValidationError as exc:
            raise PluginToolError("工具参数不符合完整 Schema") from exc
        if tool.risk == "external_write":
            if self._action_store is None:
                raise PluginToolError("外部写入工具必须配置宿主 Action Gate")
            if self._project_id is None or not self._account_id:
                raise PluginToolError("外部写入缺少项目或账号绑定")
            action = self._action_store.prepare(
                project_id=self._project_id,
                plugin_identity=tool.identity,
                plugin_hash=tool.plugin_hash,
                schema_hash=tool.schema_hash,
                account_id=self._account_id,
                arguments=arguments,
                asset_hashes=self._asset_hashes,
            )
            return {
                "ok": True,
                "status": ActionState.PENDING_CONFIRMATION.value,
                "action_id": action.action_id,
                "revision": action.revision,
            }
        result = self._executor(tool, dict(arguments))
        if not isinstance(result, Mapping):
            raise PluginToolError("插件返回结果不是对象")
        return dict(result)

    def execute_action(
        self,
        action_id: str,
        *,
        grants: Sequence[CapabilityGrant],
        current_account_id: str,
    ) -> dict[str, Any]:
        """用户确认后执行冻结调用；超时进入未知且绝不自动重试。"""
        if self._action_store is None:
            raise PluginToolError("宿主未配置 Action Gate")
        action = self._action_store.get(action_id)
        tool = self._catalog.resolve(action.plugin_identity)
        if tool.plugin_hash != action.plugin_hash or tool.schema_hash != action.schema_hash:
            raise PluginToolError("Action 绑定的 Plugin 或 Schema 已变化")
        if current_account_id != action.account_id:
            raise PluginToolError("Action 绑定账号已变化")
        if not any(
            grant.subject == tool.plugin_name
            and grant.project_id == action.project_id
            and grant.version_hash == tool.plugin_hash
            and grant.active()
            and tool.capabilities <= grant.capabilities
            for grant in grants
        ):
            raise PluginToolError("Action 执行授权已失效")
        try:
            _validate_instance(action.arguments, tool.input_schema)
        except ValidationError as exc:
            raise PluginToolError("Action 冻结参数不再符合 Schema") from exc
        self._action_store.begin_execution(action_id)
        try:
            result = self._executor(tool, dict(action.arguments))
            if not isinstance(result, Mapping):
                raise PluginToolError("插件返回结果不是对象")
        except TimeoutError:
            finished = self._action_store.finish(
                action_id,
                state=ActionState.UNKNOWN,
                result={"message": "外部写入超时，结果未知；禁止自动重试"},
            )
        except Exception:
            finished = self._action_store.finish(
                action_id,
                state=ActionState.FAILED,
                result={"message": "插件执行失败"},
            )
        else:
            finished = self._action_store.finish(
                action_id,
                state=ActionState.SUCCEEDED,
                result=dict(result),
            )
        return {
            "ok": finished.state is ActionState.SUCCEEDED,
            "status": finished.state.value,
            "action_id": finished.action_id,
            "result": dict(finished.result or {}),
        }


def _provider_name(tool: PluginTool) -> str:
    digest = hashlib.sha256(tool.identity.encode("utf-8")).hexdigest()[:10]
    prefix = re.sub(r"[^A-Za-z0-9_]", "_", f"{tool.plugin_name}_{tool.name}")[:48]
    return f"{prefix}_{digest}"


def _terms(value: str) -> set[str]:
    lowered = value.casefold()
    tokens = set(re.findall(r"[a-z0-9_.-]+|[\u4e00-\u9fff]", lowered))
    chinese = "".join(re.findall(r"[\u4e00-\u9fff]", lowered))
    tokens.update(chinese[index : index + 2] for index in range(max(0, len(chinese) - 1)))
    return {token for token in tokens if token}


def _score(terms: set[str], tool: PluginTool, manifest_aliases: tuple[str, ...]) -> int:
    fields = (
        (tool.plugin_name, 8),
        *((alias, 12) for alias in manifest_aliases),
        *((alias, 8) for alias in tool.aliases),
        (tool.name, 5),
        (tool.description, 4),
        *((tag, 6) for tag in tool.task_tags),
    )
    score = 0
    for text, weight in fields:
        normalized = text.casefold()
        field_terms = _terms(text)
        score += sum(weight for term in terms if term in normalized or term in field_terms)
    return score


def _validate_schema_shape(schema: Mapping[str, Any], *, depth: int = 0) -> None:
    if depth > 32:
        raise PluginToolError("工具 Schema 嵌套过深")
    try:
        json.dumps(schema, ensure_ascii=False)
    except (TypeError, ValueError) as exc:
        raise PluginToolError("工具 Schema 不是有效 JSON") from exc
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise PluginToolError("工具 Schema 不符合 Draft 2020-12") from exc
    properties = schema.get("properties", {})
    for child in properties.values():
        if isinstance(child, Mapping):
            _validate_schema_shape(child, depth=depth + 1)
    items = schema.get("items")
    if isinstance(items, Mapping):
        _validate_schema_shape(items, depth=depth + 1)


def _validate_instance(value: Any, schema: Mapping[str, Any]) -> None:
    Draft202012Validator(schema).validate(value)
