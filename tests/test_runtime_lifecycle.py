from __future__ import annotations

import asyncio

import pytest

from looklift.agent_adapter import (
    AgentImage,
    AgentRunInput,
    ScriptedAgentEvent,
    AgentEventKind,
)
from looklift.domain_pack import compile_domain_pack
from looklift.domain_pack_types import DomainPackRequest, VersionedJson, VersionedText
from looklift.fake_agent_adapter import FakeAgentAdapter
from looklift.runtime_lifecycle import RuntimeCapabilityError, RuntimeLifecycleEngine
from looklift.runtime_registry import RuntimeDefinition, RuntimeRegistry
from looklift.builtin_runtimes import builtin_runtime_registry


def _run_input() -> AgentRunInput:
    pack = compile_domain_pack(
        DomainPackRequest(
            system_contract=VersionedText("system", 1, "禁止正式提交。"),
            domain_contract=VersionedText("domain", 1, "只生成白盒候选。"),
            tool_contract=VersionedJson("tools", 1, {"tools": ["render_candidate"]}),
            user_goal="自然提亮",
            run_context={"photo": "proxy"},
        )
    )
    return AgentRunInput("run", "attempt", pack, AgentImage("image/jpeg", b"jpeg"), "fake")


def test_lifecycle_streams_normalized_events_and_disposes():
    async def exercise():
        adapter = FakeAgentAdapter(
            [ScriptedAgentEvent(AgentEventKind.RUN_FINISHED, {"outcome": "completed"})]
        )
        registry = RuntimeRegistry()
        registry.register(
            RuntimeDefinition(
                "fake",
                "fake",
                capabilities=frozenset({"proxy_image", "structured_terminal"}),
                permission_profile=frozenset({"proxy_image", "structured_terminal"}),
            )
        )
        engine = RuntimeLifecycleEngine(registry, factories={"fake": lambda: adapter})
        events = [
            event
            async for event in engine.start(
                "fake", _run_input(), required_capabilities={"proxy_image"}
            )
        ]
        await engine.dispose("run")
        return events

    events = asyncio.run(exercise())
    assert [event.sequence for event in events] == [1, 2]
    assert events[-1].kind is AgentEventKind.RUN_FINISHED


def test_lifecycle_rejects_missing_capability_without_fallback():
    registry = RuntimeRegistry()
    registry.register(RuntimeDefinition("fake", "fake"))
    engine = RuntimeLifecycleEngine(
        registry,
        factories={"fake": lambda: FakeAgentAdapter([])},
    )

    async def exercise():
        return [
            event
            async for event in engine.start(
                "fake", _run_input(), required_capabilities={"proxy_image"}
            )
        ]

    with pytest.raises(RuntimeCapabilityError, match="proxy_image"):
        asyncio.run(exercise())


def test_lifecycle_rejects_unknown_runtime_instead_of_selecting_another():
    registry = RuntimeRegistry()
    registry.register(RuntimeDefinition("fake", "fake"))
    engine = RuntimeLifecycleEngine(
        registry,
        factories={"fake": lambda: FakeAgentAdapter([])},
    )

    async def exercise():
        return [event async for event in engine.start("missing", _run_input())]

    with pytest.raises(ValueError, match="未知 Runtime"):
        asyncio.run(exercise())


def test_builtin_registry_declares_api_pi_and_fake_harnesses():
    registry = builtin_runtime_registry()
    assert [item.runtime_id for item in registry.list()] == [
        "pydantic-api",
        "pi-cli",
        "fake",
    ]
    assert registry.get("pi-cli").supports_resume is True
    assert registry.get("pydantic-api").input_transport == "provider_message"
