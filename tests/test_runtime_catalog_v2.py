from __future__ import annotations

import asyncio

import pytest

from looklift.agent_adapter import AgentAdapter, AgentRunInput
from looklift.builtin_runtimes import builtin_runtime_registry
from looklift.runtime_lifecycle import RuntimeLifecycleEngine, RuntimeLifecycleError
from looklift.runtime_registry import RuntimeSupportLevel
from looklift.runtime_stream import JsonLineStreamParser, RuntimeStreamError
from tests.test_runtime_lifecycle import _run_input


def test_builtin_catalog_exposes_five_user_runtimes_and_hides_compatibility_entries() -> None:
    registry = builtin_runtime_registry()

    assert [item.runtime_id for item in registry.list(selectable_only=True)] == [
        "claude-code",
        "codex-cli",
        "pi-cli",
        "deepseek-cli",
        "openai-api",
    ]
    assert registry.get("pi-cli").support_level is RuntimeSupportLevel.STABLE
    assert registry.get("fake").selectable is False
    assert all(item.contract_version == 2 for item in registry.list(selectable_only=True))


def test_runtime_lifecycle_timeout_cancels_and_disposes_adapter() -> None:
    class HangingAdapter(AgentAdapter):
        def __init__(self) -> None:
            self.cancelled = False
            self.disposed = False

        async def start(self, _run_input: AgentRunInput):
            await asyncio.sleep(1)
            if False:
                yield

        async def cancel(self, _run_id: str) -> None:
            self.cancelled = True

        async def dispose(self, _run_id: str) -> None:
            self.disposed = True

    async def exercise() -> HangingAdapter:
        adapter = HangingAdapter()
        engine = RuntimeLifecycleEngine(
            builtin_runtime_registry(), factories={"fake": lambda: adapter}
        )
        with pytest.raises(RuntimeLifecycleError, match="超时"):
            async for _event in engine.start(
                "fake", _run_input(), timeout_seconds=0.01
            ):
                pass
        assert engine.active_run_ids == ()
        return adapter

    adapter = asyncio.run(exercise())
    assert adapter.cancelled is True
    assert adapter.disposed is True


def test_json_line_parser_handles_chunk_boundaries_and_terminal_event() -> None:
    parser = JsonLineStreamParser()

    assert parser.feed(b'{"type":"text_delta","payload":{"text":"a"') == ()
    events = parser.feed(
        b'}}\n{"type":"run_finished","payload":{"outcome":"completed"}}\n'
    )

    assert [event.kind.value for event in events] == ["text_delta", "run_finished"]
    assert parser.finish() == ()


def test_json_line_parser_rejects_unknown_event_without_leaking_payload() -> None:
    parser = JsonLineStreamParser()

    with pytest.raises(RuntimeStreamError, match="事件格式不合法") as captured:
        parser.feed(b'{"type":"unknown","payload":{"token":"secret"}}\n')

    assert "secret" not in str(captured.value)
