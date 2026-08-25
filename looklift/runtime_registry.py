"""API/CLI/Fake Harness 的声明式 Runtime Registry。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


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
