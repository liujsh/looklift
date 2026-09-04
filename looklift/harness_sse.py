"""Daemon 侧 Harness 事件到 SSE 的异步桥接。"""
from __future__ import annotations

from collections.abc import AsyncIterator

from .agent_adapter import AgentAdapter, AgentEvent, AgentRunInput
from .harness_events import encode_sse


async def stream_adapter(adapter: AgentAdapter, run_input: AgentRunInput) -> AsyncIterator[bytes]:
    """逐事件产出 SSE 帧；适配器异常转换为安全的失败帧由上层处理。"""
    async for event in adapter.start(run_input):
        yield encode_sse(event)
