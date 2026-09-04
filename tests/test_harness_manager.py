import asyncio

from looklift.agent_adapter import AgentEventKind, ScriptedAgentEvent
from looklift.fake_agent_adapter import FakeAgentAdapter
from looklift.harness.manager import HarnessManager, sse_events
from looklift.runtime_lifecycle import RuntimeLifecycleEngine
from looklift.runtime_registry import RuntimeDefinition, RuntimeRegistry
from tests.test_runtime_lifecycle import _run_input


def test_manager_bridges_lifecycle_events_to_sse():
    registry = RuntimeRegistry()
    registry.register(RuntimeDefinition(runtime_id="api", kind="api", endpoint="provider://test", capabilities=frozenset(), permission_profile=frozenset()))
    lifecycle = RuntimeLifecycleEngine(registry, factories={"api": lambda: FakeAgentAdapter([ScriptedAgentEvent(AgentEventKind.RUN_FINISHED, {"outcome": "completed"})])})
    async def collect():
        return [frame async for frame in sse_events(HarnessManager(lifecycle), "api", _run_input())]
    frames = asyncio.run(collect())
    assert len(frames) == 2
    assert b"run_started" in frames[0]
