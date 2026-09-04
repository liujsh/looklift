"""Harness Attempt 的异步生命周期与 SSE 事件管理。"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from ..agent_adapter import AgentAdapter, AgentEvent, AgentRunInput
from ..runtime_lifecycle import RuntimeLifecycleEngine
from .events import encode_sse


class HarnessManager:
    """统一管理 API Harness 流，确保同一 Run 只有一个消费者。"""

    def __init__(self, lifecycle: RuntimeLifecycleEngine) -> None:
        self._lifecycle = lifecycle
        self._streams: dict[str, asyncio.Task[None]] = {}

    async def events(self, runtime_id: str, run_input: AgentRunInput, *, timeout: float | None = None) -> AsyncIterator[AgentEvent]:
        """直接透传 Lifecycle 事件；调用方负责编码为 SSE。"""
        async for event in self._lifecycle.start(runtime_id, run_input, timeout_seconds=timeout):
            yield event

    async def cancel(self, run_id: str) -> None:
        await self._lifecycle.cancel(run_id)


async def sse_events(manager: HarnessManager, runtime_id: str, run_input: AgentRunInput, *, timeout: float | None = None) -> AsyncIterator[bytes]:
    async for event in manager.events(runtime_id, run_input, timeout=timeout):
        yield encode_sse(event)
