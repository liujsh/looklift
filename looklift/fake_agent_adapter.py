"""默认测试使用的确定性 Fake Harness Adapter。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable, Mapping
from typing import Any

from .agent_adapter import (
    AgentAdapterError,
    AgentEvent,
    AgentEventKind,
    AgentRunInput,
    ScriptedAgentEvent,
)


class FakeAgentAdapter:
    """按脚本发出归一事件，不触网、不调用真实 Provider。"""

    def __init__(self, events: Iterable[ScriptedAgentEvent]) -> None:
        self._events = tuple(events)
        if any(event.kind is AgentEventKind.RUN_STARTED for event in self._events):
            raise ValueError("run_started 由 Adapter 自动生成，不能写入脚本")
        self._started: set[tuple[str, str]] = set()
        self._active: dict[str, str] = {}
        self._cancelled: set[tuple[str, str]] = set()
        self._disposed: set[str] = set()

    async def start(self, run_input: AgentRunInput) -> AsyncIterator[AgentEvent]:
        run_id = run_input.run_id
        attempt_key = (run_id, run_input.attempt_id)
        if run_id in self._disposed:
            raise AgentAdapterError(f"Run {run_id} 已经释放")
        if attempt_key in self._started:
            raise AgentAdapterError(f"Attempt {run_input.attempt_id} 已经启动")
        if run_id in self._active:
            raise AgentAdapterError(f"Run {run_id} 已有活动 Attempt")

        self._started.add(attempt_key)
        self._active[run_id] = run_input.attempt_id
        sequence = 1
        try:
            yield self._event(run_input, sequence, AgentEventKind.RUN_STARTED, {})
            sequence += 1

            for scripted in self._events:
                await asyncio.sleep(0)
                if attempt_key in self._cancelled:
                    yield self._cancelled_event(run_input, sequence)
                    return
                yield self._event(
                    run_input,
                    sequence,
                    scripted.kind,
                    scripted.payload,
                )
                sequence += 1
                if scripted.kind.terminal:
                    return

            if attempt_key in self._cancelled:
                yield self._cancelled_event(run_input, sequence)
                return
            yield self._event(
                run_input,
                sequence,
                AgentEventKind.RUN_FAILED,
                {
                    "code": "missing_terminal_event",
                    "message": "Harness 未产生终态事件",
                },
            )
        finally:
            if self._active.get(run_id) == run_input.attempt_id:
                self._active.pop(run_id)

    async def cancel(self, run_id: str) -> None:
        attempt_id = self._active.get(run_id)
        if attempt_id is not None:
            self._cancelled.add((run_id, attempt_id))

    async def dispose(self, run_id: str) -> None:
        await self.cancel(run_id)
        self._disposed.add(run_id)

    @staticmethod
    def _event(
        run_input: AgentRunInput,
        sequence: int,
        kind: AgentEventKind,
        payload: Mapping[str, Any],
    ) -> AgentEvent:
        return AgentEvent(
            kind=kind,
            run_id=run_input.run_id,
            attempt_id=run_input.attempt_id,
            sequence=sequence,
            payload=payload,
        )

    @classmethod
    def _cancelled_event(
        cls,
        run_input: AgentRunInput,
        sequence: int,
    ) -> AgentEvent:
        return cls._event(
            run_input,
            sequence,
            AgentEventKind.RUN_FINISHED,
            {"outcome": "cancelled"},
        )
