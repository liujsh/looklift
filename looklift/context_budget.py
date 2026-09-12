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
        end = _oldest_removable_group_end(prepared)
        removed = prepared[1:end]
        del prepared[1:end]
        dropped += sum(len(json.dumps(item, ensure_ascii=False)) for item in removed)
    if not dropped:
        return prepared, None
    return prepared, {
        "original_hash": original,
        "retained_messages": len(prepared),
        "dropped_chars": dropped,
        "budget_chars": budget,
        "reason": "context_budget",
    }


def _oldest_removable_group_end(messages: list[dict[str, Any]]) -> int:
    """返回首个旧消息事实组末端，工具调用与结果必须一起淘汰。"""
    first = messages[1]
    if first.get("role") != "assistant" or not isinstance(first.get("tool_calls"), list):
        return 2
    call_ids = {
        call.get("id")
        for call in first["tool_calls"]
        if isinstance(call, dict) and isinstance(call.get("id"), str)
    }
    end = 2
    while end < len(messages) - 1:
        item = messages[end]
        if item.get("role") != "tool" or item.get("tool_call_id") not in call_ids:
            break
        end += 1
    return end
