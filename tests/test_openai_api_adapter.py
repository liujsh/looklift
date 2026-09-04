from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from looklift.agent_adapter import AgentEventKind
from looklift.openai_api_adapter import OpenAiApiAdapter
from looklift.provider_snapshot import ProviderProtocol, ProviderSnapshot
from looklift.scoped_tool_gateway import GatewayToolResult, ScopedToolGrant
from tests.test_runtime_lifecycle import _run_input


def _sse(value: dict) -> bytes:
    return f"data: {json.dumps(value)}\n\n".encode()


def test_openai_adapter_runs_tool_feedback_loop_through_gateway() -> None:
    class Runtime:
        def __init__(self) -> None:
            self.latest_candidate = SimpleNamespace(
                candidate_id="candidate-1", changes=(), preview_jpeg=b"jpeg", metrics={}
            )
            self.binding = SimpleNamespace(base_version_id="a" * 64)

        def cancel(self) -> None:
            pass

    class Gateway:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def bind(self, _runtime) -> ScopedToolGrant:
            return ScopedToolGrant("token", 999)

        def call(self, _token, name, _arguments) -> GatewayToolResult:
            self.calls.append(name)
            if name == "render_candidate":
                return GatewayToolResult(
                    {"ok": True, "candidate_id": "candidate-1", "revision": 1},
                    b"jpeg",
                )
            return GatewayToolResult({"ok": True, "outcome": "candidate_ready"})

        def revoke(self, _token) -> None:
            pass

    class Transport:
        def __init__(self) -> None:
            self.round = 0

        async def stream(self, _snapshot, request, *, api_key):
            assert api_key == "sk-test"
            if self.round == 1:
                assert request["messages"][-1]["role"] == "tool"
            name = "render_candidate" if self.round == 0 else "finish_candidate"
            arguments = (
                {"operations": [], "intent": "检查"}
                if self.round == 0
                else {"outcome": "candidate_ready", "candidate_id": "candidate-1", "summary": "完成"}
            )
            self.round += 1
            yield _sse(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": f"call-{self.round}",
                                        "function": {
                                            "name": name,
                                            "arguments": json.dumps(arguments),
                                        },
                                    }
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
            )

    snapshot = ProviderSnapshot(
        "openai",
        "https://api.openai.com/v1",
        "gpt-5",
        "credential://openai/default",
        ProviderProtocol.OPENAI_CHAT_COMPLETIONS,
        4096,
        1,
    )
    gateway = Gateway()
    adapter = OpenAiApiAdapter(
        snapshot_resolver=lambda _input: snapshot,
        credential_resolver=lambda _ref: "sk-test",
        runtime_resolver=lambda _input: Runtime(),
        transport=Transport(),
        tool_gateway=gateway,
    )

    async def exercise():
        return [event async for event in adapter.start(_run_input())]

    events = asyncio.run(exercise())
    assert gateway.calls == ["render_candidate", "finish_candidate"]
    assert AgentEventKind.CANDIDATE_CREATED in [event.kind for event in events]
    assert events[-1].kind is AgentEventKind.RUN_FINISHED
    assert events[-1].payload["verifier"]["status"] == "pass"
    assert events[-1].payload["user_review"]["confirmed"] is False


def test_openai_adapter_emits_tool_loop_limit_after_three_rounds() -> None:
    class Runtime:
        latest_candidate = None
        binding = SimpleNamespace(base_version_id="a" * 64)

        def cancel(self) -> None:
            pass

    class Gateway:
        def bind(self, _runtime) -> ScopedToolGrant:
            return ScopedToolGrant("token", 999)

        def call(self, _token, name, _arguments) -> GatewayToolResult:
            return GatewayToolResult({"ok": True, "tool": name})

        def revoke(self, _token) -> None:
            pass

    class Transport:
        round = 0

        async def stream(self, _snapshot, request, *, api_key):
            self.round += 1
            yield _sse(
                {
                    "choices": [
                        {
                            "delta": {
                                "tool_calls": [
                                    {
                                        "index": 0,
                                        "id": f"call-{self.round}",
                                        "function": {
                                            "name": "render_candidate",
                                            "arguments": json.dumps({"operations": [], "intent": "检查"}),
                                        },
                                    }
                                ]
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
            )

    snapshot = ProviderSnapshot(
        "openai",
        "https://api.openai.com/v1",
        "gpt-5",
        "credential://openai/default",
        ProviderProtocol.OPENAI_CHAT_COMPLETIONS,
        4096,
        1,
    )
    adapter = OpenAiApiAdapter(
        snapshot_resolver=lambda _input: snapshot,
        credential_resolver=lambda _ref: "sk-test",
        runtime_resolver=lambda _input: Runtime(),
        transport=Transport(),
        tool_gateway=Gateway(),
    )

    async def exercise():
        return [event async for event in adapter.start(_run_input())]

    events = asyncio.run(exercise())
    assert events[-1].kind is AgentEventKind.RUN_FAILED
    assert events[-1].payload["code"] == "tool_loop_limit"
