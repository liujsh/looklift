"""API/CLI/Fake Harness 的声明式 Runtime Registry。"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass


class RuntimeDefinitionError(ValueError):
    pass


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
        if self.stream_format not in {"agent_events", "pydantic_events", "jsonl"}:
            raise RuntimeDefinitionError("Runtime stream_format 不受支持")


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
