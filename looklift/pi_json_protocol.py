"""Pi 原生 JSON 事件的有限解析与脱敏投影。"""

from __future__ import annotations

from typing import Any


_TOOL_NAMES = frozenset({"render_candidate", "finish_candidate"})


def pi_tool_identity(source: dict[str, Any]) -> tuple[str, str]:
    name = source.get("toolName")
    call_id = source.get("toolCallId")
    if name not in _TOOL_NAMES or not isinstance(call_id, str) or not call_id:
        raise ValueError("Pi 工具事件身份无效")
    return name, call_id


def pi_text_delta(source: dict[str, Any]) -> str | None:
    if source.get("type") != "message_update":
        return None
    update = source.get("assistantMessageEvent")
    if not isinstance(update, dict) or update.get("type") != "text_delta":
        return None
    delta = update.get("delta")
    if not isinstance(delta, str):
        raise ValueError("Pi 文本增量无效")
    return delta


def pi_usage_payload(source: dict[str, Any]) -> dict[str, int] | None:
    if source.get("type") != "message_end":
        return None
    message = source.get("message")
    usage = message.get("usage") if isinstance(message, dict) else None
    if not isinstance(usage, dict):
        return None
    return {
        "input_tokens": _safe_int(usage.get("input")),
        "output_tokens": _safe_int(usage.get("output")),
        "cache_read_tokens": _safe_int(usage.get("cacheRead")),
        "cache_write_tokens": _safe_int(usage.get("cacheWrite")),
    }


def _safe_int(value: object) -> int:
    return value if isinstance(value, int) and value >= 0 else 0
