"""统一 Agent Adapter ABI 与 Fake Harness 的离线契约测试。"""

from __future__ import annotations

import asyncio
from dataclasses import replace

import pytest

from looklift.agent_adapter import (
    AgentAdapterError,
    AgentEventKind,
    AgentImage,
    AgentRunInput,
    ScriptedAgentEvent,
)
from looklift.fake_agent_adapter import FakeAgentAdapter
from looklift.domain_pack_types import CompiledDomainPack


def _run_input() -> AgentRunInput:
    return AgentRunInput(
        run_id="run-1",
        attempt_id="attempt-1",
        domain_pack=_compiled_domain_pack(),
        proxy_image=AgentImage(media_type="image/jpeg", content=b"safe-proxy"),
        model="fake-model",
    )


def _compiled_domain_pack(**changes: object) -> CompiledDomainPack:
    values = {
        "instructions": "领域契约与本轮上下文",
        "user_message": "自然修复这张照片",
        "source_hashes": (),
        "omitted_sources": (),
        "content_hash": "a" * 64,
        "estimated_tokens": 16,
        **changes,
    }
    return CompiledDomainPack(**values)  # type: ignore[arg-type]


def test_fake_adapter_emits_normalized_ordered_events() -> None:
    async def exercise() -> list:
        adapter = FakeAgentAdapter(
            [
                ScriptedAgentEvent(AgentEventKind.TEXT_DELTA, {"text": "分析中"}),
                ScriptedAgentEvent(
                    AgentEventKind.TOOL_STARTED,
                    {"tool_name": "render_candidate", "call_id": "call-1"},
                ),
                ScriptedAgentEvent(
                    AgentEventKind.CANDIDATE_CREATED,
                    {"candidate_id": "candidate-1"},
                ),
                ScriptedAgentEvent(
                    AgentEventKind.RUN_FINISHED,
                    {"outcome": "candidate_ready"},
                ),
            ]
        )
        return [event async for event in adapter.start(_run_input())]

    events = asyncio.run(exercise())

    assert [event.kind for event in events] == [
        AgentEventKind.RUN_STARTED,
        AgentEventKind.TEXT_DELTA,
        AgentEventKind.TOOL_STARTED,
        AgentEventKind.CANDIDATE_CREATED,
        AgentEventKind.RUN_FINISHED,
    ]
    assert [event.sequence for event in events] == [1, 2, 3, 4, 5]
    assert {(event.run_id, event.attempt_id) for event in events} == {
        ("run-1", "attempt-1")
    }


def test_cancel_finishes_current_stream_without_replaying_later_events() -> None:
    async def exercise() -> list:
        adapter = FakeAgentAdapter(
            [
                ScriptedAgentEvent(AgentEventKind.TEXT_DELTA, {"text": "不会出现"}),
                ScriptedAgentEvent(
                    AgentEventKind.RUN_FINISHED,
                    {"outcome": "candidate_ready"},
                ),
            ]
        )
        stream = adapter.start(_run_input())
        first = await anext(stream)
        await adapter.cancel("run-1")
        return [first, *[event async for event in stream]]

    events = asyncio.run(exercise())

    assert [event.kind for event in events] == [
        AgentEventKind.RUN_STARTED,
        AgentEventKind.RUN_FINISHED,
    ]
    assert events[-1].payload == {"outcome": "cancelled"}


def test_terminal_event_stops_script_and_duplicate_start_is_rejected() -> None:
    async def exercise() -> None:
        adapter = FakeAgentAdapter(
            [
                ScriptedAgentEvent(
                    AgentEventKind.RUN_FAILED,
                    {"code": "provider_failed", "message": "模拟失败"},
                ),
                ScriptedAgentEvent(AgentEventKind.TEXT_DELTA, {"text": "越过终态"}),
            ]
        )
        assert [event.kind async for event in adapter.start(_run_input())] == [
            AgentEventKind.RUN_STARTED,
            AgentEventKind.RUN_FAILED,
        ]
        with pytest.raises(AgentAdapterError, match="已经启动"):
            await anext(adapter.start(_run_input()))

    asyncio.run(exercise())


def test_same_run_can_start_a_new_attempt_after_terminal_event() -> None:
    async def exercise() -> list:
        adapter = FakeAgentAdapter(
            [
                ScriptedAgentEvent(
                    AgentEventKind.RUN_FINISHED,
                    {"outcome": "no_change_needed"},
                )
            ]
        )
        first = [event async for event in adapter.start(_run_input())]
        second_input = replace(_run_input(), attempt_id="attempt-2")
        second = [event async for event in adapter.start(second_input)]
        return [first, second]

    attempts = asyncio.run(exercise())

    assert [events[0].attempt_id for events in attempts] == ["attempt-1", "attempt-2"]
    assert [events[0].sequence for events in attempts] == [1, 1]


def test_script_without_terminal_event_is_normalized_to_failure() -> None:
    async def exercise() -> list:
        adapter = FakeAgentAdapter(
            [ScriptedAgentEvent(AgentEventKind.TEXT_DELTA, {"text": "未正常结束"})]
        )
        return [event async for event in adapter.start(_run_input())]

    events = asyncio.run(exercise())

    assert events[-1].kind is AgentEventKind.RUN_FAILED
    assert events[-1].payload["code"] == "missing_terminal_event"


def test_dispose_is_idempotent_and_prevents_new_start() -> None:
    async def exercise() -> None:
        adapter = FakeAgentAdapter([])
        await adapter.dispose("run-1")
        await adapter.dispose("run-1")
        with pytest.raises(AgentAdapterError, match="已经释放"):
            await anext(adapter.start(_run_input()))

    asyncio.run(exercise())


@pytest.mark.parametrize("media_type", ["image/png", "text/plain", "image/jpeg;evil"])
def test_proxy_image_only_accepts_fixed_safe_media_types(media_type: str) -> None:
    with pytest.raises(ValueError, match="媒体类型"):
        AgentImage(media_type=media_type, content=b"proxy")


def test_run_input_rejects_untrusted_hash_and_empty_prompt() -> None:
    with pytest.raises(ValueError, match="Hash"):
        AgentRunInput(
            run_id="run-1",
            attempt_id="attempt-1",
            domain_pack=_compiled_domain_pack(content_hash="not-a-hash"),
            proxy_image=AgentImage("image/jpeg", b"proxy"),
            model="fake-model",
        )

    with pytest.raises(ValueError, match="Prompt"):
        AgentRunInput(
            run_id="run-1",
            attempt_id="attempt-1",
            domain_pack=_compiled_domain_pack(instructions=""),
            proxy_image=AgentImage("image/jpeg", b"proxy"),
            model="fake-model",
        )
