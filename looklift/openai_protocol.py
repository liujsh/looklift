"""OpenAI-compatible 请求与 SSE 增量事件协议。"""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .provider_snapshot import ProviderSnapshot


class OpenAiProtocolError(ValueError):
    """上游协议无效；错误正文不包含原始响应。"""


@dataclass(frozen=True)
class OpenAiProtocolEvent:
    kind: str
    payload: Mapping[str, Any]


def build_openai_request(
    snapshot: ProviderSnapshot,
    *,
    instructions: str,
    user_message: str,
    proxy_jpeg: bytes,
    tools: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    image = base64.b64encode(proxy_jpeg).decode("ascii")
    return {
        "model": snapshot.model,
        "messages": [
            {"role": "system", "content": instructions},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_message},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{image}"},
                    },
                ],
            },
        ],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool.get("description", ""),
                    "parameters": tool["inputSchema"],
                },
            }
            for tool in tools
        ],
        "tool_choice": "auto",
        "max_tokens": snapshot.max_tokens,
        "stream": True,
        "stream_options": {"include_usage": True},
    }


class OpenAiSseParser:
    def __init__(self, *, max_buffer_bytes: int = 8 * 1024 * 1024) -> None:
        self._buffer = bytearray()
        self._limit = max_buffer_bytes
        self._tool_calls: dict[int, dict[str, str]] = {}

    def feed(self, chunk: bytes) -> tuple[OpenAiProtocolEvent, ...]:
        self._buffer.extend(chunk)
        if len(self._buffer) > self._limit:
            self._buffer.clear()
            raise OpenAiProtocolError("Provider 流响应超过大小限制")
        events: list[OpenAiProtocolEvent] = []
        while b"\n\n" in self._buffer:
            block, _, remaining = self._buffer.partition(b"\n\n")
            self._buffer = bytearray(remaining)
            events.extend(self._parse_block(bytes(block)))
        return tuple(events)

    def finish(self) -> tuple[OpenAiProtocolEvent, ...]:
        if not self._buffer.strip():
            return ()
        block = bytes(self._buffer)
        self._buffer.clear()
        return tuple(self._parse_block(block))

    def _parse_block(self, block: bytes) -> list[OpenAiProtocolEvent]:
        data = b"\n".join(
            line[5:].lstrip() for line in block.splitlines() if line.startswith(b"data:")
        )
        if not data:
            return []
        if data == b"[DONE]":
            return [OpenAiProtocolEvent("done", {})]
        try:
            value = json.loads(data)
            choices = value.get("choices", [])
            choice = choices[0] if choices else {}
            delta = choice.get("delta", {})
            events: list[OpenAiProtocolEvent] = []
            content = delta.get("content")
            if isinstance(content, str) and content:
                events.append(OpenAiProtocolEvent("text", {"text": content}))
            for raw in delta.get("tool_calls", []):
                index = int(raw.get("index", 0))
                current = self._tool_calls.setdefault(
                    index, {"id": "", "name": "", "arguments": ""}
                )
                current["id"] = raw.get("id") or current["id"]
                function = raw.get("function", {})
                current["name"] += function.get("name", "")
                current["arguments"] += function.get("arguments", "")
            if choice.get("finish_reason") == "tool_calls":
                for index in sorted(self._tool_calls):
                    call = self._tool_calls[index]
                    events.append(
                        OpenAiProtocolEvent(
                            "tool_call",
                            {
                                "id": call["id"],
                                "name": call["name"],
                                "arguments": json.loads(call["arguments"]),
                            },
                        )
                    )
                self._tool_calls.clear()
            usage = value.get("usage")
            if isinstance(usage, Mapping):
                events.append(OpenAiProtocolEvent("usage", dict(usage)))
            return events
        except (TypeError, ValueError, json.JSONDecodeError) as exc:
            raise OpenAiProtocolError("Provider SSE 事件格式不合法") from exc
