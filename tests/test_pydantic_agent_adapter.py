"""内嵌 Pydantic AI Adapter 的离线最小候选闭环。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

from pydantic_ai import BinaryContent
from pydantic_ai.messages import ModelMessage, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel

from looklift.agent_adapter import AgentEventKind, AgentImage, AgentRunInput
from looklift.agent_tool_contract import RenderCandidateInput
from looklift.candidate_runtime import CandidateRuntime
from looklift.candidate_runtime_types import InMemoryRunAuthority, RunBinding
from looklift.domain_pack_types import CompiledDomainPack
from looklift.pydantic_agent_adapter import PydanticAgentAdapter


class FakeRenderer:
    def render(self, _image_path, analysis: dict) -> bytes:
        from io import BytesIO

        from PIL import Image

        output = BytesIO()
        exposure = float(analysis["basic"]["exposure"])
        value = max(0, min(255, round(128 + exposure * 20)))
        Image.new("RGB", (8, 8), (value, value, value)).save(output, format="JPEG")
        return output.getvalue()


def _compiled_pack() -> CompiledDomainPack:
    return CompiledDomainPack(
        instructions="只通过候选工具完成修图，不得提交正式版本。",
        user_message="自然提亮当前照片",
        source_hashes=(),
        omitted_sources=(),
        content_hash="a" * 64,
        estimated_tokens=16,
    )


def _run_input() -> AgentRunInput:
    return AgentRunInput(
        run_id="run-1",
        attempt_id="attempt-1",
        domain_pack=_compiled_pack(),
        proxy_image=AgentImage("image/jpeg", b"\xff\xd8proxy\xff\xd9"),
        model="fake-model",
    )


def _runtime(
    sample_analysis: dict,
    *,
    attempt_id: str = "attempt-1",
) -> CandidateRuntime:
    binding = RunBinding(
        run_id="run-1",
        attempt_id=attempt_id,
        lease="lease-1",
        base_version_id="version-1",
        image_path=Path(__file__),
    )
    return CandidateRuntime(
        binding=binding,
        authority=InMemoryRunAuthority(binding),
        baseline_analysis=deepcopy(sample_analysis),
        renderer=FakeRenderer(),
    )


def _render_args(path: str, value: float) -> dict[str, Any]:
    return {
        "operations": [
            {
                "type": "scalar",
                "path": path,
                "mode": "delta",
                "value": value,
                "reason": "离线测试",
            }
        ],
        "intent": "生成候选",
        "template_strength": None,
    }


def _latest_candidate_id(messages: list[ModelMessage]) -> str:
    returns = [
        part
        for message in messages
        for part in message.parts
        if isinstance(part, ToolReturnPart)
        and part.tool_name == "render_candidate"
        and isinstance(part.content, dict)
        and part.content.get("ok") is True
    ]
    return str(returns[-1].content["candidate_id"])


def _scripted_model(
    mode: str,
    captured: list[list[ModelMessage]],
) -> FunctionModel:
    turn = 0

    async def stream(
        messages: list[ModelMessage],
        _info: AgentInfo,
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal turn
        captured.append(messages)
        current = turn
        turn += 1
        if mode == "no_change":
            yield {0: _finish_call("no_change_needed", None, "无需修改")}
            return
        if current == 0:
            yield {
                0: DeltaToolCall(
                    name="render_candidate",
                    json_args=json.dumps(_render_args("basic.exposure", 0.2)),
                    tool_call_id="render-1",
                )
            }
            return
        if mode == "two_candidates" and current == 1:
            assert any(
                isinstance(part, UserPromptPart)
                and not isinstance(part.content, str)
                and any(isinstance(item, BinaryContent) for item in part.content)
                for message in messages
                for part in message.parts
            )
            yield {
                0: DeltaToolCall(
                    name="render_candidate",
                    json_args=json.dumps(_render_args("basic.contrast", -5)),
                    tool_call_id="render-2",
                )
            }
            return
        yield {
            0: _finish_call(
                "candidate_ready",
                _latest_candidate_id(messages),
                "候选已经可以复核",
            )
        }

    return FunctionModel(stream_function=stream)


def _finish_call(outcome: str, candidate_id: str | None, summary: str) -> DeltaToolCall:
    return DeltaToolCall(
        name="finish_candidate",
        json_args=json.dumps(
            {
                "outcome": outcome,
                "candidate_id": candidate_id,
                "summary": summary,
                "review_items": [],
                "uncertainties": [],
                "limitations": [],
            }
        ),
        tool_call_id="finish-1",
    )


def test_adapter_runs_candidate_image_feedback_and_structured_finish(
    sample_analysis: dict,
) -> None:
    captured: list[list[ModelMessage]] = []
    runtime = _runtime(sample_analysis)
    adapter = PydanticAgentAdapter(
        model_resolver=lambda _input: _scripted_model("candidate", captured),
        runtime_resolver=lambda _input: runtime,
    )

    async def exercise():
        return [event async for event in adapter.start(_run_input())]

    events = asyncio.run(exercise())

    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert AgentEventKind.CANDIDATE_CREATED in [event.kind for event in events]
    assert events[-1].kind is AgentEventKind.RUN_FINISHED
    assert events[-1].payload["outcome"] == "candidate_ready"
    assert runtime.finished is not None
    assert len(captured) == 2
    assert any(
        isinstance(part, UserPromptPart)
        and not isinstance(part.content, str)
        and any(isinstance(item, BinaryContent) for item in part.content)
        for message in captured[1]
        for part in message.parts
    )


def test_adapter_supports_two_candidate_revisions(sample_analysis: dict) -> None:
    runtime = _runtime(sample_analysis)
    adapter = PydanticAgentAdapter(
        model_resolver=lambda _input: _scripted_model("two_candidates", []),
        runtime_resolver=lambda _input: runtime,
    )

    async def exercise():
        return [event async for event in adapter.start(_run_input())]

    events = asyncio.run(exercise())

    assert len(runtime.candidates) == 2
    assert sum(event.kind is AgentEventKind.CANDIDATE_CREATED for event in events) == 2
    assert events[-1].payload["candidate_id"] == runtime.latest_candidate.candidate_id


def test_adapter_can_finish_without_rendering(sample_analysis: dict) -> None:
    runtime = _runtime(sample_analysis)
    adapter = PydanticAgentAdapter(
        model_resolver=lambda _input: _scripted_model("no_change", []),
        runtime_resolver=lambda _input: runtime,
    )

    async def exercise():
        return [event async for event in adapter.start(_run_input())]

    events = asyncio.run(exercise())

    assert runtime.candidates == ()
    assert events[-1].kind is AgentEventKind.RUN_FINISHED
    assert events[-1].payload["outcome"] == "no_change_needed"


def test_adapter_cancel_revokes_runtime_and_finishes_stream(sample_analysis: dict) -> None:
    started = asyncio.Event()

    async def slow_stream(
        _messages: list[ModelMessage],
        _info: AgentInfo,
    ) -> AsyncIterator[str]:
        started.set()
        await asyncio.sleep(60)
        yield "不应完成"

    runtime = _runtime(sample_analysis)
    adapter = PydanticAgentAdapter(
        model_resolver=lambda _input: FunctionModel(stream_function=slow_stream),
        runtime_resolver=lambda _input: runtime,
    )

    async def exercise():
        stream = adapter.start(_run_input())
        first = await anext(stream)
        pending = asyncio.create_task(anext(stream))
        await started.wait()
        await adapter.cancel("run-1")
        terminal = await asyncio.wait_for(pending, timeout=1)
        return first, terminal

    first, terminal = asyncio.run(exercise())

    assert first.kind is AgentEventKind.RUN_STARTED
    assert terminal.kind is AgentEventKind.RUN_FINISHED
    assert terminal.payload["outcome"] == "cancelled"
    rejected = runtime.render_candidate(
        # 取消后的晚到工具即使拿到原绑定也不能创建候选。
        RenderCandidateInput(**_render_args("basic.exposure", 0.2))
    )
    assert rejected.error is not None
    assert rejected.error.code == "cancelled"


def test_provider_failure_is_sanitized_and_terminal(sample_analysis: dict) -> None:
    async def fail_stream(
        _messages: list[ModelMessage],
        _info: AgentInfo,
    ) -> AsyncIterator[str]:
        raise RuntimeError("secret provider payload")
        yield "unreachable"

    adapter = PydanticAgentAdapter(
        model_resolver=lambda _input: FunctionModel(stream_function=fail_stream),
        runtime_resolver=lambda _input: _runtime(sample_analysis),
    )

    async def exercise():
        return [event async for event in adapter.start(_run_input())]

    events = asyncio.run(exercise())

    assert events[-1].kind is AgentEventKind.RUN_FAILED
    assert events[-1].payload == {
        "code": "provider_failed",
        "message": "模型 Harness 执行失败",
    }


def test_same_run_can_start_new_attempt_but_not_replay_attempt(
    sample_analysis: dict,
) -> None:
    runtimes = {
        "attempt-1": _runtime(sample_analysis),
        "attempt-2": _runtime(sample_analysis, attempt_id="attempt-2"),
    }
    adapter = PydanticAgentAdapter(
        model_resolver=lambda _input: _scripted_model("no_change", []),
        runtime_resolver=lambda value: runtimes[value.attempt_id],
    )

    async def exercise():
        first = [event async for event in adapter.start(_run_input())]
        second_input = replace(_run_input(), attempt_id="attempt-2")
        second = [event async for event in adapter.start(second_input)]
        replay = [event async for event in adapter.start(_run_input())]
        return first, second, replay

    first, second, replay = asyncio.run(exercise())

    assert first[-1].kind is AgentEventKind.RUN_FINISHED
    assert second[-1].kind is AgentEventKind.RUN_FINISHED
    assert replay[-1].kind is AgentEventKind.RUN_FAILED
    assert replay[-1].payload["code"] == "duplicate_attempt"
