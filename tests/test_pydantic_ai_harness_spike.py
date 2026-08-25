"""pydantic-ai-slim 作为内嵌 Harness 的离线可行性门。"""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from openai import AsyncOpenAI
from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    BinaryContent,
    CancellationToken,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelResponse,
    RunCancelled,
    TextPart,
    ToolCallPart,
    ToolReturn,
)
from pydantic_ai.messages import ModelMessage, ToolReturnPart, UserPromptPart
from pydantic_ai.models.function import AgentInfo, DeltaToolCall, FunctionModel
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider


def _tool_call_then_finish(
    captured_requests: list[list[ModelMessage]],
) -> FunctionModel:
    call_count = 0
    stream_count = 0

    def respond(messages: list[ModelMessage], _info: AgentInfo) -> ModelResponse:
        nonlocal call_count
        captured_requests.append(messages)
        call_count += 1
        if call_count == 1:
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="render_candidate",
                        args={"exposure_delta": 0.2},
                        tool_call_id="call-1",
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="候选已完成")])

    async def stream(
        messages: list[ModelMessage],
        _info: AgentInfo,
    ) -> AsyncIterator[str | dict[int, DeltaToolCall]]:
        nonlocal stream_count
        captured_requests.append(messages)
        stream_count += 1
        if stream_count == 1:
            yield {
                0: DeltaToolCall(
                    name="render_candidate",
                    json_args='{"exposure_delta":0.2}',
                    tool_call_id="call-1",
                )
            }
        else:
            yield "候选已完成"

    return FunctionModel(respond, stream_function=stream)


def _agent(model: FunctionModel) -> Agent[None, str]:
    agent = Agent(model, instructions="只使用候选工具", output_type=str)

    @agent.tool_plain
    def render_candidate(exposure_delta: float) -> ToolReturn[dict[str, Any]]:
        return ToolReturn(
            return_value={
                "candidate_id": "candidate-1",
                "exposure_delta": exposure_delta,
            },
            content=[
                "当前候选预览",
                BinaryContent(data=b"\xff\xd8fake-jpeg\xff\xd9", media_type="image/jpeg"),
            ],
            metadata={"remaining_tool_calls": 1},
        )

    return agent


def test_tool_result_image_is_returned_to_next_model_request() -> None:
    async def exercise() -> tuple[Any, list[list[ModelMessage]]]:
        requests: list[list[ModelMessage]] = []
        result = await _agent(_tool_call_then_finish(requests)).run(
            "自然修复这张照片"
        )
        return result, requests

    result, requests = asyncio.run(exercise())

    assert result.output == "候选已完成"
    assert len(requests) == 2
    second_request_parts = [part for message in requests[1] for part in message.parts]
    assert any(
        isinstance(part, ToolReturnPart)
        and part.tool_name == "render_candidate"
        and part.content["candidate_id"] == "candidate-1"
        for part in second_request_parts
    )
    assert any(
        isinstance(part, UserPromptPart)
        and any(isinstance(item, BinaryContent) for item in part.content)
        for part in second_request_parts
    )


def test_typed_stream_contains_tool_call_result_and_terminal_events() -> None:
    async def exercise() -> list[type]:
        agent = _agent(_tool_call_then_finish([]))
        async with agent.run_stream_events("自然修复这张照片") as events:
            return [type(event) async for event in events]

    event_types = asyncio.run(exercise())

    assert FunctionToolCallEvent in event_types
    assert FunctionToolResultEvent in event_types
    assert AgentRunResultEvent in event_types


def test_cancellation_token_interrupts_active_model_request() -> None:
    async def exercise() -> None:
        started = asyncio.Event()

        async def slow_response(
            _messages: list[ModelMessage],
            _info: AgentInfo,
        ) -> ModelResponse:
            started.set()
            await asyncio.sleep(60)
            return ModelResponse(parts=[TextPart(content="不应完成")])

        agent = Agent(FunctionModel(slow_response), output_type=str)
        token = CancellationToken()
        task = asyncio.create_task(agent.run("开始", cancellation_token=token))
        await started.wait()
        token.cancel()
        with pytest.raises(RunCancelled):
            await asyncio.wait_for(task, timeout=1)

    asyncio.run(exercise())


def test_openai_compatible_provider_can_represent_local_ollama_endpoint() -> None:
    provider = OpenAIProvider(
        base_url="http://127.0.0.1:11434/v1",
        api_key="local-placeholder",
    )
    model = OpenAIChatModel("qwen3-vl", provider=provider)

    assert model.model_name == "qwen3-vl"
    assert model.system == "openai"


def test_openai_provider_serializes_proxy_image_without_network() -> None:
    async def exercise() -> dict[str, Any]:
        captured: dict[str, Any] = {}

        async def respond(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "id": "chatcmpl-test",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "test-vl",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "完成"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 1,
                        "completion_tokens": 1,
                        "total_tokens": 2,
                    },
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond),
            base_url="https://mock.invalid/v1",
        ) as client:
            provider = OpenAIProvider(
                openai_client=AsyncOpenAI(
                    api_key="test-key",
                    base_url="https://mock.invalid/v1",
                    http_client=client,
                )
            )
            agent = Agent(OpenAIChatModel("test-vl", provider=provider))
            await agent.run(
                [
                    "查看安全代理图",
                    BinaryContent(
                        data=b"\xff\xd8proxy\xff\xd9",
                        media_type="image/jpeg",
                    ),
                ]
            )
        return captured

    payload = asyncio.run(exercise())

    content = payload["messages"][-1]["content"]
    image = next(item for item in content if item["type"] == "image_url")
    assert image["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_anthropic_provider_serializes_proxy_image_without_network() -> None:
    async def exercise() -> dict[str, Any]:
        captured: dict[str, Any] = {}

        async def respond(request: httpx.Request) -> httpx.Response:
            captured.update(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "id": "msg-test",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-test",
                    "content": [{"type": "text", "text": "完成"}],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                },
            )

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(respond),
            base_url="https://mock.invalid",
        ) as client:
            provider = AnthropicProvider(
                api_key="test-key",
                base_url="https://mock.invalid",
                http_client=client,
            )
            agent = Agent(AnthropicModel("claude-test", provider=provider))
            await agent.run(
                [
                    "查看安全代理图",
                    BinaryContent(
                        data=b"\xff\xd8proxy\xff\xd9",
                        media_type="image/jpeg",
                    ),
                ]
            )
        return captured

    payload = asyncio.run(exercise())

    content = payload["messages"][-1]["content"]
    image = next(item for item in content if item["type"] == "image")
    assert image["source"]["media_type"] == "image/jpeg"
    assert image["source"]["type"] == "base64"
