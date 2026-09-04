"""Attempt 输入快照与异步流管理基础设施。"""
from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from typing import Any

from ..agent_adapter import AgentRunInput
from ..harness_events import encode_sse
from ..runtime_lifecycle import RuntimeLifecycleEngine


@dataclass(frozen=True)
class AgentRunInputSnapshot:
    run_id: str
    attempt_id: str
    runtime_id: str
    model: str
    domain_pack_hash: str
    image_hash: str
    config_version: int

    @classmethod
    def from_input(cls, run_input: AgentRunInput, runtime_id: str, *, config_version: int, image_hash: str) -> "AgentRunInputSnapshot":
        return cls(run_input.run_id, run_input.attempt_id, runtime_id, run_input.model, run_input.domain_pack.content_hash, image_hash, config_version)


class AttemptStreamManager:
    """把 Lifecycle 异步事件转成可取消的 SSE 迭代器。"""

    def __init__(self, lifecycle: RuntimeLifecycleEngine) -> None:
        self.lifecycle = lifecycle
        self._cancel_tokens: dict[str, asyncio.Event] = {}

    async def stream(self, runtime_id: str, run_input: AgentRunInput, *, timeout: float | None = None):
        token = asyncio.Event()
        self._cancel_tokens[run_input.run_id] = token
        try:
            async for event in self.lifecycle.start(runtime_id, run_input, timeout_seconds=timeout):
                if token.is_set():
                    break
                yield encode_sse(event)
        finally:
            self._cancel_tokens.pop(run_input.run_id, None)

    async def cancel(self, run_id: str) -> None:
        token = self._cancel_tokens.get(run_id)
        if token is not None:
            token.set()
        await self.lifecycle.cancel(run_id)
