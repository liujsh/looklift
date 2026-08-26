from __future__ import annotations

import asyncio

import pytest

from looklift.agent_adapter import AgentEventKind, ScriptedAgentEvent
from looklift.builtin_runtimes import builtin_runtime_registry
from looklift.fake_agent_adapter import FakeAgentAdapter
from looklift.runtime_lifecycle import RuntimeLifecycleEngine
from tests.test_runtime_lifecycle import _run_input


@pytest.mark.parametrize(
    "runtime_id",
    ["claude-code", "codex-cli", "pi-cli", "deepseek-cli", "openai-api"],
)
def test_user_runtime_definitions_share_offline_lifecycle_contract(
    runtime_id: str,
) -> None:
    adapter = FakeAgentAdapter(
        [ScriptedAgentEvent(AgentEventKind.RUN_FINISHED, {"outcome": "completed"})]
    )
    engine = RuntimeLifecycleEngine(
        builtin_runtime_registry(), factories={runtime_id: lambda: adapter}
    )

    async def exercise():
        return [
            event
            async for event in engine.start(
                runtime_id, _run_input(), required_capabilities={"proxy_image"}
            )
        ]

    events = asyncio.run(exercise())
    assert events[0].kind is AgentEventKind.RUN_STARTED
    assert events[-1].kind is AgentEventKind.RUN_FINISHED
    assert events[-1].payload["runtime"]["runtime_id"] == runtime_id
