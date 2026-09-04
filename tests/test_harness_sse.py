import asyncio
import json

from looklift.agent_adapter import AgentEventKind, ScriptedAgentEvent
from looklift.harness_sse import stream_adapter
from looklift.fake_agent_adapter import FakeAgentAdapter
from tests.test_runtime_lifecycle import _run_input


def test_stream_adapter_emits_ordered_sse_frames():
    async def collect():
        adapter = FakeAgentAdapter([ScriptedAgentEvent(AgentEventKind.RUN_FINISHED, {"outcome": "completed"})])
        return [frame async for frame in stream_adapter(adapter, _run_input())]

    frames = asyncio.run(collect())
    assert frames
    payloads = [json.loads(frame.split(b"data: ", 1)[1]) for frame in frames]
    assert payloads[0]["type"] == str(AgentEventKind.RUN_STARTED)
    assert [item["sequence"] for item in payloads] == list(range(1, len(payloads) + 1))
