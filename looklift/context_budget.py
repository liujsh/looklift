"""BYOK Harness 的上下文预算、摘要与硬截断。"""
from __future__ import annotations

import hashlib
import json
from typing import Any

MAX_MESSAGE_CHARS = 12_000
MAX_TOOL_RESULT_CHARS = 8_000
DEFAULT_BUDGET_CHARS = 96_000


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def prepare_messages(messages: list[dict[str, Any]], budget: int = DEFAULT_BUDGET_CHARS) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """保留系统/当前目标，优先压缩旧消息，最后按单条上限截断。"""
    original = _digest(messages)
    prepared: list[dict[str, Any]] = []
    dropped = 0
    for index, message in enumerate(messages):
        item = dict(message)
        content = item.get("content")
        if isinstance(content, str) and len(content) > MAX_MESSAGE_CHARS:
            item["content"] = content[:MAX_MESSAGE_CHARS] + "…[已截断]"
            dropped += len(content) - MAX_MESSAGE_CHARS
        if item.get("role") == "tool" and isinstance(item.get("content"), str) and len(item["content"]) > MAX_TOOL_RESULT_CHARS:
            value = item["content"]
            item["content"] = value[:MAX_TOOL_RESULT_CHARS] + "…[工具结果已截断]"
            dropped += len(value) - MAX_TOOL_RESULT_CHARS
        prepared.append(item)
    while sum(len(json.dumps(item, ensure_ascii=False)) for item in prepared) > budget and len(prepared) > 2:
        removed = prepared.pop(1)
        dropped += len(json.dumps(removed, ensure_ascii=False))
    if not dropped:
        return prepared, None
    return prepared, {
        "original_hash": original,
        "retained_messages": len(prepared),
        "dropped_chars": dropped,
        "budget_chars": budget,
        "reason": "context_budget",
    }
