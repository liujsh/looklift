import json

from looklift.agent_adapter import AgentEvent, AgentEventKind
from looklift.harness_events import encode_sse


def test_harness_event_is_encoded_as_stable_sse_frame():
    frame = encode_sse(AgentEvent(AgentEventKind.CONTEXT_COMPACTION, "run", "attempt", 1, {"dropped_chars": 10}))
    assert frame.startswith(b"event: harness\ndata: ")
    data = json.loads(frame.split(b"data: ", 1)[1])
    assert data["type"] == "context_compaction"
    assert data["payload"]["dropped_chars"] == 10
