"""BYOK Harness 的上下文预算、摘要与硬截断。"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable

MAX_MESSAGE_CHARS = 12_000
MAX_TOOL_RESULT_CHARS = 8_000
DEFAULT_BUDGET_CHARS = 96_000


class ContextBudgetError(ValueError):
    """必需上下文在保留结构与输出空间后仍超过模型预算。"""


@dataclass(frozen=True)
class ContextBudgetPolicy:
    max_input_tokens: int = 32_000
    output_reserve_tokens: int = 4_000
    image_tokens: int = 1_500

    def __post_init__(self) -> None:
        if (
            self.max_input_tokens <= 0
            or self.output_reserve_tokens <= 0
            or self.image_tokens <= 0
            or self.output_reserve_tokens >= self.max_input_tokens
        ):
            raise ContextBudgetError("统一上下文预算无效")


TokenCounter = Callable[[str], int]


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def prepare_messages(
    messages: list[dict[str, Any]],
    budget: int = DEFAULT_BUDGET_CHARS,
    *,
    token_budget: int | None = None,
    token_counter: TokenCounter | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    """保留系统/当前目标，优先压缩旧消息，最后按单条上限截断。"""
    original = _digest(messages)
    prepared: list[dict[str, Any]] = []
    dropped = 0
    protected = _protected_message_indexes(messages) if token_budget is not None else set()
    for index, message in enumerate(messages):
        item = dict(message)
        content = item.get("content")
        if index not in protected and isinstance(content, str) and len(content) > MAX_MESSAGE_CHARS:
            item["content"] = content[:MAX_MESSAGE_CHARS] + "…[已截断]"
            dropped += len(content) - MAX_MESSAGE_CHARS
        if (
            index not in protected
            and item.get("role") == "tool"
            and isinstance(item.get("content"), str)
            and len(item["content"]) > MAX_TOOL_RESULT_CHARS
        ):
            value = item["content"]
            item["content"] = value[:MAX_TOOL_RESULT_CHARS] + "…[工具结果已截断]"
            dropped += len(value) - MAX_TOOL_RESULT_CHARS
        prepared.append(item)
    def measure(items: list[dict[str, Any]]) -> int:
        if token_budget is None:
            return sum(len(json.dumps(item, ensure_ascii=False)) for item in items)
        return _estimate_tokens(items, token_counter=token_counter)

    limit = budget if token_budget is None else token_budget
    while measure(prepared) > limit:
        removable = _oldest_removable_range(prepared, unified=token_budget is not None)
        if removable is None:
            break
        start, end = removable
        removed = prepared[start:end]
        del prepared[start:end]
        dropped += sum(len(json.dumps(item, ensure_ascii=False)) for item in removed)
    if not dropped:
        return prepared, None
    return prepared, {
        "original_hash": original,
        "retained_messages": len(prepared),
        "dropped_chars": dropped,
        "budget_chars": budget if token_budget is None else None,
        "budget_tokens": token_budget,
        "reason": "context_budget",
    }


def prepare_openai_context(
    request: dict[str, Any],
    *,
    policy: ContextBudgetPolicy = ContextBudgetPolicy(),
    token_counter: TokenCounter | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """在一次发送边界统一计量消息、Schema、资料、结果、图片与输出预留。"""
    messages = request.get("messages")
    tools = request.get("tools", [])
    if not isinstance(messages, list) or not all(isinstance(item, dict) for item in messages):
        raise ContextBudgetError("消息上下文结构无效")
    if not isinstance(tools, list):
        raise ContextBudgetError("工具 Schema 上下文结构无效")
    output_reserve = request.get("max_tokens", policy.output_reserve_tokens)
    if (
        not isinstance(output_reserve, int)
        or isinstance(output_reserve, bool)
        or output_reserve <= 0
    ):
        raise ContextBudgetError("Provider 输出预留无效")
    schema_tokens = _estimate_tokens(tools, token_counter=token_counter)
    image_count = _count_images(messages)
    image_tokens = image_count * policy.image_tokens
    fixed = schema_tokens + image_tokens + output_reserve
    if schema_tokens + output_reserve >= policy.max_input_tokens:
        raise ContextBudgetError("必需工具 Schema 超过上下文预算，不能截断")
    if fixed >= policy.max_input_tokens:
        raise ContextBudgetError("必需图片与工具 Schema 超过上下文预算")
    message_budget = policy.max_input_tokens - fixed
    prepared, compaction = prepare_messages(
        messages,
        token_budget=message_budget,
        token_counter=token_counter,
    )
    message_tokens = _estimate_tokens(prepared, token_counter=token_counter)
    if message_tokens > message_budget:
        raise ContextBudgetError("系统约束与当前目标超过上下文预算")
    categories = _message_categories(prepared, token_counter=token_counter)
    categories.update(
        {
            "schemas": schema_tokens,
            "images": image_tokens,
            "output_reserve": output_reserve,
        }
    )
    return prepared, {
        "method": "provider_tokenizer" if token_counter is not None else "utf8_bytes_upper_bound",
        "max_input_tokens": policy.max_input_tokens,
        "total_tokens": sum(categories.values()),
        "categories": categories,
        "image_count": image_count,
        "compaction": compaction,
    }


def _estimate_tokens(value: Any, *, token_counter: TokenCounter | None) -> int:
    encoded = json.dumps(
        _without_image_payloads(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if token_counter is not None:
        count = token_counter(encoded)
        if not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ContextBudgetError("Provider tokenizer 返回无效计量")
        return count
    # UTF-8 字节数是未知 tokenizer 下的保守上界，不声称等同真实 token。
    return len(encoded.encode("utf-8"))


def _without_image_payloads(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[image-bytes]"
            if key == "url" and isinstance(item, str) and item.startswith("data:image/")
            else _without_image_payloads(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_without_image_payloads(item) for item in value]
    return value


def _count_images(value: Any) -> int:
    if isinstance(value, dict):
        return sum(
            1
            if key == "url" and isinstance(item, str) and item.startswith("data:image/")
            else _count_images(item)
            for key, item in value.items()
        )
    if isinstance(value, list):
        return sum(_count_images(item) for item in value)
    return 0


def _message_categories(
    messages: list[dict[str, Any]], *, token_counter: TokenCounter | None
) -> dict[str, int]:
    categories = {"messages": 0, "resources": 0, "results": 0}
    for message in messages:
        if message.get("role") == "tool":
            category = "results"
        elif message.get("context_type") in {"skill", "reference"}:
            category = "resources"
        else:
            category = "messages"
        categories[category] += _estimate_tokens(message, token_counter=token_counter)
    return categories


def _protected_message_indexes(messages: list[dict[str, Any]]) -> set[int]:
    """保护开头系统契约、原始任务与最新完整事实组。"""
    prefix = _required_prefix_length(messages)
    protected = set(range(prefix))
    groups = _fact_groups(messages, prefix)
    if groups:
        protected.update(range(*groups[-1]))
    return protected


def _required_prefix_length(messages: list[dict[str, Any]]) -> int:
    end = 0
    while end < len(messages) and messages[end].get("role") == "system":
        end += 1
    if end < len(messages):
        end += 1
    return end


def _fact_groups(
    messages: list[dict[str, Any]], start: int
) -> list[tuple[int, int]]:
    groups: list[tuple[int, int]] = []
    index = start
    while index < len(messages):
        end = _message_group_end(messages, index)
        groups.append((index, end))
        index = end
    return groups


def _oldest_removable_range(
    messages: list[dict[str, Any]], *, unified: bool
) -> tuple[int, int] | None:
    if unified:
        prefix = _required_prefix_length(messages)
        groups = _fact_groups(messages, prefix)
        return groups[0] if len(groups) > 1 else None
    if len(messages) <= 2:
        return None
    end = _message_group_end(messages, 1)
    return None if end == len(messages) else (1, end)


def _message_group_end(messages: list[dict[str, Any]], start: int) -> int:
    """返回指定消息事实组末端，工具调用与结果不可拆分。"""
    first = messages[start]
    if first.get("role") != "assistant" or not isinstance(first.get("tool_calls"), list):
        return start + 1
    call_ids = {
        call.get("id")
        for call in first["tool_calls"]
        if isinstance(call, dict) and isinstance(call.get("id"), str)
    }
    end = start + 1
    while end < len(messages):
        item = messages[end]
        if item.get("role") != "tool" or item.get("tool_call_id") not in call_ids:
            break
        end += 1
    return end
