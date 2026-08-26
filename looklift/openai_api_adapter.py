"""不依赖通用 Agent 框架的 OpenAI-compatible API Harness。"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from typing import Any, Protocol

from .agent_adapter import AgentEvent, AgentEventKind, AgentRunInput
from .candidate_runtime import CandidateRuntime
from .openai_protocol import OpenAiSseParser, build_openai_request
from .provider_snapshot import ProviderSnapshot
from .scoped_tool_gateway import ScopedToolGateway, agent_tool_definitions
from .verifier import CandidateVerifier, UserReviewGate
from .verified_agent_adapter import CandidateReviewError, build_candidate_review


class OpenAiTransport(Protocol):
    def stream(
        self,
        snapshot: ProviderSnapshot,
        request: Mapping[str, Any],
        *,
        api_key: str | None,
    ) -> AsyncIterator[bytes]: ...


SnapshotResolver = Callable[[AgentRunInput], ProviderSnapshot]
CredentialResolver = Callable[[str], str]
RuntimeResolver = Callable[[AgentRunInput], CandidateRuntime]


@dataclass
class _ActiveApi:
    runtime: CandidateRuntime
    token: str
    cancelled: bool = False


class OpenAiApiAdapter:
    """单 Provider Attempt；工具循环只调用统一 Scoped Gateway。"""

    def __init__(
        self,
        *,
        snapshot_resolver: SnapshotResolver,
        credential_resolver: CredentialResolver,
        runtime_resolver: RuntimeResolver,
        transport: OpenAiTransport,
        tool_gateway: ScopedToolGateway | None = None,
        verifier: CandidateVerifier | None = None,
        review_gate: UserReviewGate | None = None,
    ) -> None:
        self._snapshot_resolver = snapshot_resolver
        self._credential_resolver = credential_resolver
        self._runtime_resolver = runtime_resolver
        self._transport = transport
        self._gateway = tool_gateway or ScopedToolGateway()
        self._verifier = verifier or CandidateVerifier()
        self._review_gate = review_gate or UserReviewGate()
        self._active: dict[str, _ActiveApi] = {}
        self._attempts: set[tuple[str, str]] = set()

    async def start(self, run_input: AgentRunInput) -> AsyncIterator[AgentEvent]:
        sequence = 0

        def event(kind: AgentEventKind, payload: Mapping[str, Any]) -> AgentEvent:
            nonlocal sequence
            sequence += 1
            return AgentEvent(
                kind, run_input.run_id, run_input.attempt_id, sequence, payload
            )

        attempt = (run_input.run_id, run_input.attempt_id)
        if attempt in self._attempts or run_input.run_id in self._active:
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "duplicate_attempt", "message": "同一 Attempt 不能重复启动"},
            )
            return
        try:
            snapshot = self._snapshot_resolver(run_input)
            runtime = self._runtime_resolver(run_input)
            api_key = (
                self._credential_resolver(snapshot.api_key_ref)
                if snapshot.api_key_ref is not None
                else None
            )
            grant = self._gateway.bind(runtime)
        except Exception:
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "configuration_failed", "message": "API Harness 配置无效"},
            )
            return

        self._attempts.add(attempt)
        active = _ActiveApi(runtime, grant.token)
        self._active[run_input.run_id] = active
        yield event(
            AgentEventKind.RUN_STARTED,
            {
                "provider": snapshot.provider_id,
                "model": snapshot.model,
                "config_version": snapshot.config_version,
            },
        )
        request = build_openai_request(
            snapshot,
            instructions=run_input.domain_pack.instructions,
            user_message=run_input.domain_pack.user_message,
            proxy_jpeg=run_input.proxy_image.content,
            tools=agent_tool_definitions(),
        )
        try:
            for _round in range(8):
                if active.cancelled:
                    yield event(AgentEventKind.RUN_FINISHED, {"outcome": "cancelled"})
                    return
                parser = OpenAiSseParser()
                protocol_events = []
                async for chunk in self._transport.stream(
                    snapshot, request, api_key=api_key
                ):
                    protocol_events.extend(parser.feed(chunk))
                protocol_events.extend(parser.finish())
                tool_called = False
                for source in protocol_events:
                    if source.kind == "text":
                        yield event(AgentEventKind.TEXT_DELTA, source.payload)
                    elif source.kind == "usage":
                        yield event(AgentEventKind.USAGE_UPDATED, source.payload)
                    elif source.kind == "tool_call":
                        tool_called = True
                        name = str(source.payload["name"])
                        call_id = str(source.payload["id"])
                        arguments = source.payload["arguments"]
                        yield event(
                            AgentEventKind.TOOL_STARTED,
                            {"tool_name": name, "call_id": call_id},
                        )
                        result = self._gateway.call(grant.token, name, arguments)
                        payload = dict(result.payload)
                        yield event(
                            AgentEventKind.TOOL_COMPLETED,
                            {"tool_name": name, "call_id": call_id, "result": payload},
                        )
                        if name == "render_candidate" and payload.get("ok") is True:
                            yield event(AgentEventKind.CANDIDATE_CREATED, payload)
                        if name == "finish_candidate" and payload.get("ok") is True:
                            if payload.get("outcome") == "candidate_ready":
                                try:
                                    payload.update(
                                        build_candidate_review(
                                            runtime,
                                            verifier=self._verifier,
                                            review_gate=self._review_gate,
                                        )
                                    )
                                except CandidateReviewError as exc:
                                    yield event(
                                        AgentEventKind.RUN_FAILED,
                                        {
                                            "code": exc.code,
                                            "message": str(exc),
                                            "verifier": exc.verifier,
                                        },
                                    )
                                    return
                            yield event(AgentEventKind.RUN_FINISHED, payload)
                            return
                        request["messages"].extend(
                            [
                                {
                                    "role": "assistant",
                                    "tool_calls": [
                                        {
                                            "id": call_id,
                                            "type": "function",
                                            "function": {
                                                "name": name,
                                                "arguments": json.dumps(
                                                    arguments, ensure_ascii=False
                                                ),
                                            },
                                        }
                                    ],
                                },
                                {
                                    "role": "tool",
                                    "tool_call_id": call_id,
                                    "content": json.dumps(payload, ensure_ascii=False),
                                },
                            ]
                        )
                if not tool_called:
                    break
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "missing_terminal", "message": "模型未返回合法终态"},
            )
        except Exception:
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "provider_failed", "message": "API Harness 执行失败"},
            )
        finally:
            self._gateway.revoke(grant.token)
            self._active.pop(run_input.run_id, None)

    async def cancel(self, run_id: str) -> None:
        active = self._active.get(run_id)
        if active is not None:
            active.cancelled = True
            active.runtime.cancel()
            self._gateway.revoke(active.token)

    async def dispose(self, run_id: str) -> None:
        await self.cancel(run_id)
