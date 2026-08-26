"""API/CLI/Fake Harness 的声明式 Runtime Registry。"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum


_STREAM_FORMATS = frozenset(
    {"agent_events", "pydantic_events", "jsonl", "json_rpc", "rpc", "sse"}
)


class RuntimeDefinitionError(ValueError):
    pass


class RuntimeSupportLevel(StrEnum):
    """Runtime 对用户公开的支持等级。"""

    STABLE = "stable"
    EXPERIMENTAL = "experimental"


@dataclass(frozen=True)
class RuntimeDefinition:
    runtime_id: str
    kind: str
    command: str | None = None
    endpoint: str | None = None
    capabilities: frozenset[str] = frozenset()
    models: tuple[str, ...] = ()
    permission_profile: frozenset[str] = frozenset()
    input_transport: str = "domain_pack"
    stream_format: str = "agent_events"
    supports_resume: bool = False
    supports_mcp: bool = False
    contract_version: int = 1
    display_name: str | None = None
    version_probe: str | None = None
    model_probe: str | None = None
    event_parser: str | None = None
    support_level: RuntimeSupportLevel = RuntimeSupportLevel.EXPERIMENTAL
    supports_cancel: bool = True
    supports_timeout: bool = True

    def __post_init__(self) -> None:
        if not self.runtime_id or self.kind not in {"api", "cli", "fake"}:
            raise RuntimeDefinitionError("Runtime id/kind 无效")
        if self.kind == "cli" and not self.command:
            raise RuntimeDefinitionError("CLI Runtime 必须声明 command")
        if self.kind == "api" and not self.endpoint:
            raise RuntimeDefinitionError("API Runtime 必须声明 endpoint")
        if self.kind == "fake" and (self.command or self.endpoint):
            raise RuntimeDefinitionError("Fake Runtime 不应声明外部入口")
        if not self.permission_profile.issubset(self.capabilities):
            raise RuntimeDefinitionError("permission_profile 不能扩大 Runtime capabilities")
        if self.input_transport not in {"domain_pack", "provider_message", "cli_workspace"}:
            raise RuntimeDefinitionError("Runtime input_transport 不受支持")
        if self.stream_format not in _STREAM_FORMATS:
            raise RuntimeDefinitionError("Runtime stream_format 不受支持")
        if self.contract_version not in {1, 2}:
            raise RuntimeDefinitionError("Runtime Definition 版本不受支持")
        try:
            support_level = RuntimeSupportLevel(self.support_level)
        except ValueError as exc:
            raise RuntimeDefinitionError("Runtime 支持等级无效") from exc
        object.__setattr__(self, "support_level", support_level)
        if self.display_name is None and self.contract_version == 1:
            object.__setattr__(self, "display_name", self.runtime_id)
        if self.contract_version == 2:
            required = {
                "display_name": self.display_name,
                "version_probe": self.version_probe,
                "model_probe": self.model_probe,
                "event_parser": self.event_parser,
            }
            if any(not isinstance(value, str) or not value.strip() for value in required.values()):
                raise RuntimeDefinitionError("Runtime Definition v2 声明不完整")
        if not isinstance(self.supports_cancel, bool) or not isinstance(
            self.supports_timeout, bool
        ):
            raise RuntimeDefinitionError("Runtime 取消或超时能力声明无效")


@dataclass(frozen=True)
class RuntimeProbeResult:
    runtime_id: str
    available: bool
    version: str | None = None
    authenticated: bool = False
    models: tuple[str, ...] = ()
    error: str | None = None


class RuntimeRegistry:
    def __init__(self, definitions: Mapping[str, RuntimeDefinition] | None = None) -> None:
        self._definitions: dict[str, RuntimeDefinition] = {}
        for definition in (definitions or {}).values():
            self.register(definition)

    def register(self, definition: RuntimeDefinition) -> None:
        if definition.runtime_id in self._definitions:
            raise RuntimeDefinitionError("Runtime ID 已注册")
        self._definitions[definition.runtime_id] = definition

    def get(self, runtime_id: str) -> RuntimeDefinition:
        try:
            return self._definitions[runtime_id]
        except KeyError as exc:
            raise RuntimeDefinitionError("未知 Runtime") from exc

    def list(self, *, kind: str | None = None) -> tuple[RuntimeDefinition, ...]:
        values = tuple(self._definitions.values())
        return tuple(item for item in values if kind is None or item.kind == kind)


Probe = Callable[[RuntimeDefinition], Awaitable[Mapping[str, object]]]


class RuntimeDetectionEngine:
    """并行运行声明式 Runtime 的外部探测，并隔离单项故障。"""

    def __init__(
        self,
        registry: RuntimeRegistry,
        *,
        probes: Mapping[str, Probe],
        timeout_seconds: float = 5.0,
    ) -> None:
        self._registry = registry
        self._probes = dict(probes)
        self._timeout_seconds = timeout_seconds

    async def detect_all(self) -> tuple[RuntimeProbeResult, ...]:
        return tuple(
            await asyncio.gather(
                *(self._detect(definition) for definition in self._registry.list())
            )
        )

    async def _detect(self, definition: RuntimeDefinition) -> RuntimeProbeResult:
        probe = self._probes.get(definition.runtime_id)
        if probe is None:
            return RuntimeProbeResult(
                runtime_id=definition.runtime_id,
                available=False,
                error="未配置 Runtime 探测器",
            )
        try:
            value = await asyncio.wait_for(
                probe(definition),
                timeout=self._timeout_seconds,
            )
            models = value.get("models", ())
            if not isinstance(models, tuple) or not all(
                isinstance(model, str) for model in models
            ):
                raise RuntimeDefinitionError("Runtime 模型探测结果无效")
            return RuntimeProbeResult(
                runtime_id=definition.runtime_id,
                available=True,
                version=str(value.get("version", "")) or None,
                authenticated=value.get("authenticated") is True,
                models=models,
            )
        except Exception:
            return RuntimeProbeResult(
                runtime_id=definition.runtime_id,
                available=False,
                error="Runtime 探测失败",
            )
