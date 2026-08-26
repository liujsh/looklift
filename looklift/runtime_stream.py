"""不同 Harness 流协议共用的增量解析边界。"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Protocol, runtime_checkable

from .agent_adapter import AgentEventKind, ScriptedAgentEvent


class RuntimeStreamError(ValueError):
    """上游事件无法安全归一；正文不得包含原始载荷。"""


@runtime_checkable
class RuntimeStreamParser(Protocol):
    """把无身份上游字节归一为由 Adapter 绑定身份的事件。"""

    def feed(self, chunk: bytes) -> tuple[ScriptedAgentEvent, ...]: ...

    def finish(self) -> tuple[ScriptedAgentEvent, ...]: ...


class JsonLineStreamParser:
    """解析已声明的通用 JSONL 事件，支持任意字节分块。"""

    def __init__(self, *, max_buffer_bytes: int = 8 * 1024 * 1024) -> None:
        self._buffer = bytearray()
        self._max_buffer_bytes = max_buffer_bytes

    def feed(self, chunk: bytes) -> tuple[ScriptedAgentEvent, ...]:
        if not isinstance(chunk, bytes):
            raise RuntimeStreamError("Runtime 事件格式不合法")
        self._buffer.extend(chunk)
        if len(self._buffer) > self._max_buffer_bytes:
            self._buffer.clear()
            raise RuntimeStreamError("Runtime 事件超过大小限制")
        events: list[ScriptedAgentEvent] = []
        while b"\n" in self._buffer:
            line, _, remaining = self._buffer.partition(b"\n")
            self._buffer = bytearray(remaining)
            if line.strip():
                events.append(self._parse_line(bytes(line)))
        return tuple(events)

    def finish(self) -> tuple[ScriptedAgentEvent, ...]:
        if not self._buffer.strip():
            self._buffer.clear()
            return ()
        line = bytes(self._buffer)
        self._buffer.clear()
        return (self._parse_line(line),)

    @staticmethod
    def _parse_line(line: bytes) -> ScriptedAgentEvent:
        try:
            value = json.loads(line)
            if not isinstance(value, Mapping):
                raise TypeError
            kind = AgentEventKind(value.get("type"))
            payload = value.get("payload", {})
            if not isinstance(payload, Mapping):
                raise TypeError
            return ScriptedAgentEvent(kind, payload)
        except (TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeStreamError("Runtime 事件格式不合法") from exc
