from __future__ import annotations

import asyncio
from types import SimpleNamespace

from looklift.agent_adapter import AgentEventKind, ScriptedAgentEvent
from looklift.fake_agent_adapter import FakeAgentAdapter
from looklift.verified_agent_adapter import VerifiedAgentAdapter
from tests.test_runtime_lifecycle import _run_input


def test_verified_adapter_opens_review_only_for_candidate_ready() -> None:
    runtime = SimpleNamespace(
        latest_candidate=SimpleNamespace(
            candidate_id="candidate-1", changes=(), preview_jpeg=b"jpeg", metrics={}
        ),
        binding=SimpleNamespace(base_version_id="a" * 64),
    )
    adapter = VerifiedAgentAdapter(
        FakeAgentAdapter(
            [
                ScriptedAgentEvent(
                    AgentEventKind.RUN_FINISHED,
                    {"ok": True, "outcome": "candidate_ready"},
                )
            ]
        ),
        runtime_resolver=lambda _input: runtime,
    )

    async def exercise():
        return [event async for event in adapter.start(_run_input())]

    events = asyncio.run(exercise())
    assert events[-1].kind is AgentEventKind.RUN_FINISHED
    assert events[-1].payload["verifier"]["status"] == "pass"
    assert events[-1].payload["user_review"]["confirmed"] is False
