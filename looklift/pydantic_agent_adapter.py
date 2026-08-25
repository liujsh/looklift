"""把 Pydantic AI 事件流约束为 LookLift 候选 Agent ABI。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pydantic_ai import (
    Agent,
    AgentRunResultEvent,
    BinaryContent,
    CancellationToken,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    ModelRetry,
    OutputToolCallEvent,
    OutputToolResultEvent,
    PartDeltaEvent,
    PartStartEvent,
    RunCancelled,
    RunContext,
    TextPart,
    TextPartDelta,
    ToolOutput,
    ToolReturn,
    UsageLimitExceeded,
    UsageLimits,
)
from pydantic_ai.messages import RetryPromptPart, ToolReturnPart
from pydantic_ai.models import Model

from .agent_adapter import AgentEvent, AgentEventKind, AgentRunInput
from .agent_tool_contract import (
    EditOperation,
    FinishCandidateInput,
    RenderCandidateInput,
)
from .candidate_runtime import CandidateRuntime


ModelResolver = Callable[[AgentRunInput], Model]
RuntimeResolver = Callable[[AgentRunInput], CandidateRuntime]


@dataclass
class _ActiveRun:
    token: CancellationToken
    runtime: CandidateRuntime


class PydanticAgentAdapter:
    """单 Provider、单 Attempt 的内嵌 API Harness。"""

    def __init__(
        self,
        *,
        model_resolver: ModelResolver,
        runtime_resolver: RuntimeResolver,
    ) -> None:
        self._model_resolver = model_resolver
        self._runtime_resolver = runtime_resolver
        self._active: dict[str, _ActiveRun] = {}
        self._attempts: set[tuple[str, str]] = set()
        self._disposed: set[str] = set()

    async def start(self, run_input: AgentRunInput) -> AsyncIterator[AgentEvent]:
        sequence = 0

        def event(kind: AgentEventKind, payload: Mapping[str, Any]) -> AgentEvent:
            nonlocal sequence
            sequence += 1
            return AgentEvent(
                kind=kind,
                run_id=run_input.run_id,
                attempt_id=run_input.attempt_id,
                sequence=sequence,
                payload=payload,
            )

        attempt_key = (run_input.run_id, run_input.attempt_id)
        if attempt_key in self._attempts:
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "duplicate_attempt", "message": "同一 Attempt 不能重复启动"},
            )
            return
        if run_input.run_id in self._disposed:
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "run_disposed", "message": "本轮已经释放"},
            )
            return
        if run_input.run_id in self._active:
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "run_active", "message": "本轮已有正在执行的 Attempt"},
            )
            return

        try:
            runtime = self._runtime_resolver(run_input)
            _validate_binding(run_input, runtime)
            model = self._model_resolver(run_input)
        except Exception:
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "configuration_failed", "message": "Agent 运行配置无效"},
            )
            return

        token = CancellationToken()
        self._attempts.add(attempt_key)
        self._active[run_input.run_id] = _ActiveRun(token=token, runtime=runtime)
        yield event(
            AgentEventKind.RUN_STARTED,
            {"model": run_input.model, "domain_pack_hash": run_input.domain_pack.content_hash},
        )

        agent = _build_agent(model, runtime, run_input.domain_pack.instructions)
        terminal_emitted = False
        try:
            prompt = [
                run_input.domain_pack.user_message,
                BinaryContent(
                    data=run_input.proxy_image.content,
                    media_type=run_input.proxy_image.media_type,
                ),
            ]
            async with agent.run_stream_events(
                prompt,
                run_id=run_input.run_id,
                cancellation_token=token,
                usage_limits=UsageLimits(
                    request_limit=runtime.binding.max_render_calls + 2,
                ),
            ) as stream:
                async for source in stream:
                    for kind, payload in _normalize_event(source):
                        yield event(kind, payload)
                    candidate_payload = _candidate_payload(source)
                    if candidate_payload is not None:
                        yield event(AgentEventKind.CANDIDATE_CREATED, candidate_payload)
                    if isinstance(source, AgentRunResultEvent):
                        usage = source.result.usage
                        yield event(
                            AgentEventKind.USAGE_UPDATED,
                            {
                                "requests": usage.requests,
                                "tool_calls": usage.tool_calls,
                                "input_tokens": usage.input_tokens,
                                "output_tokens": usage.output_tokens,
                            },
                        )
                        finished = runtime.finished
                        if finished is None or not finished.ok:
                            raise RuntimeError("Runtime 未接受模型终态")
                        yield event(
                            AgentEventKind.RUN_FINISHED,
                            finished.model_dump(mode="json", exclude_none=True),
                        )
                        terminal_emitted = True
        except RunCancelled:
            yield event(AgentEventKind.RUN_FINISHED, {"outcome": "cancelled"})
            terminal_emitted = True
        except UsageLimitExceeded:
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "budget_exhausted", "message": "模型请求预算已耗尽"},
            )
            terminal_emitted = True
        except Exception:
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "provider_failed", "message": "模型 Harness 执行失败"},
            )
            terminal_emitted = True
        finally:
            self._active.pop(run_input.run_id, None)

        if not terminal_emitted:
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "missing_terminal", "message": "模型未返回合法终态"},
            )

    async def cancel(self, run_id: str) -> None:
        active = self._active.get(run_id)
        if active is None:
            return
        active.runtime.cancel()
        active.token.cancel()

    async def dispose(self, run_id: str) -> None:
        await self.cancel(run_id)
        self._disposed.add(run_id)


def _build_agent(model: Model, runtime: CandidateRuntime, instructions: str) -> Agent:
    agent = Agent(
        model,
        output_type=ToolOutput(
            FinishCandidateInput,
            name="finish_candidate",
            description="结束候选生成，只记录模型终态，不提交正式版本。",
            sequential=True,
        ),
        instructions=instructions,
        max_concurrency=1,
    )

    @agent.tool_plain(sequential=True)
    def render_candidate(
        operations: tuple[EditOperation, ...],
        intent: str,
        template_strength: float | None = None,
    ) -> ToolReturn:
        """渲染白盒参数候选，并把真实 JPEG 与指标交还模型检查。"""
        result = runtime.render_candidate(
            RenderCandidateInput(
                operations=operations,
                intent=intent,
                template_strength=template_strength,
            )
        )
        payload = result.model_dump(mode="json", exclude_none=True)
        content: Sequence[str | BinaryContent] | None = None
        latest = runtime.latest_candidate
        if result.ok and latest is not None:
            content = (
                "请检查这个候选的真实渲染结果，再决定继续精修或结束。",
                BinaryContent(data=latest.preview_jpeg, media_type="image/jpeg"),
            )
        return ToolReturn(
            return_value=payload,
            content=content,
            metadata={"remaining_render_calls": result.remaining_render_calls},
        )

    @agent.output_validator
    def validate_finish(
        _ctx: RunContext[None],
        output: FinishCandidateInput,
    ) -> FinishCandidateInput:
        result = runtime.finish_candidate(output)
        if result.ok:
            return output
        if result.error is not None and result.error.correctable:
            raise ModelRetry(result.error.message)
        raise RuntimeError("Runtime 拒绝模型终态")

    return agent


def _validate_binding(run_input: AgentRunInput, runtime: CandidateRuntime) -> None:
    if (
        runtime.binding.run_id != run_input.run_id
        or runtime.binding.attempt_id != run_input.attempt_id
    ):
        raise ValueError("Runtime 身份与 Harness 输入不一致")


def _normalize_event(source: object) -> list[tuple[AgentEventKind, dict[str, Any]]]:
    if isinstance(source, PartStartEvent) and isinstance(source.part, TextPart):
        return [(AgentEventKind.TEXT_DELTA, {"text": source.part.content})]
    if isinstance(source, PartDeltaEvent) and isinstance(source.delta, TextPartDelta):
        return [(AgentEventKind.TEXT_DELTA, {"text": source.delta.content_delta})]
    if isinstance(source, (FunctionToolCallEvent, OutputToolCallEvent)):
        return [
            (
                AgentEventKind.TOOL_STARTED,
                {
                    "tool_name": source.part.tool_name,
                    "tool_call_id": source.part.tool_call_id,
                },
            )
        ]
    if isinstance(source, (FunctionToolResultEvent, OutputToolResultEvent)):
        payload: dict[str, Any] = {
            "tool_name": source.part.tool_name,
            "tool_call_id": source.part.tool_call_id,
            "ok": not isinstance(source.part, RetryPromptPart),
        }
        return [(AgentEventKind.TOOL_COMPLETED, payload)]
    return []


def _candidate_payload(source: object) -> dict[str, Any] | None:
    if not isinstance(source, FunctionToolResultEvent):
        return None
    part = source.part
    if not isinstance(part, ToolReturnPart) or part.tool_name != "render_candidate":
        return None
    if not isinstance(part.content, dict) or part.content.get("ok") is not True:
        return None
    return {
        "candidate_id": part.content["candidate_id"],
        "parent_candidate_id": part.content.get("parent_candidate_id"),
        "remaining_render_calls": part.content["remaining_render_calls"],
    }
