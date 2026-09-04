"""将统一 Harness 事件编码为前端可消费的 SSE 帧。"""
from __future__ import annotations

import json
from collections.abc import Iterable

from .agent_adapter import AgentEvent


def encode_sse(event: AgentEvent) -> bytes:
    payload = {
        "type": str(event.kind),
        "run_id": event.run_id,
        "attempt_id": event.attempt_id,
        "sequence": event.sequence,
        "payload": dict(event.payload),
    }
    return b"event: harness\ndata: " + json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode() + b"\n\n"


def encode_sse_batch(events: Iterable[AgentEvent]) -> bytes:
    return b"".join(encode_sse(event) for event in events)
