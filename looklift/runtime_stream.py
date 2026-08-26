"""不同 Harness 流协议共用的增量解析边界。"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .agent_adapter import ScriptedAgentEvent


@runtime_checkable
class RuntimeStreamParser(Protocol):
    """把无身份上游字节归一为由 Adapter 绑定身份的事件。"""

    def feed(self, chunk: bytes) -> tuple[ScriptedAgentEvent, ...]: ...

    def finish(self) -> tuple[ScriptedAgentEvent, ...]: ...
