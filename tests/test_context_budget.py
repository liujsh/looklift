import pytest

from looklift.context_budget import (
    ContextBudgetError,
    ContextBudgetPolicy,
    prepare_messages,
    prepare_openai_context,
)


def test_prepare_messages_truncates_large_tool_result_and_emits_audit():
    messages = [
        {"role": "system", "content": "contract"},
        {"role": "tool", "content": "x" * 9000},
    ]
    prepared, audit = prepare_messages(messages)
    assert len(prepared[1]["content"]) < 9000
    assert audit is not None
    assert audit["dropped_chars"] >= 1000


def test_prepare_messages_drops_old_context_when_budget_exceeded():
    messages = [{"role": "system", "content": "contract"}]
    messages.extend({"role": "user", "content": f"轮次 {i} " + "x" * 100} for i in range(10))
    prepared, audit = prepare_messages(messages, budget=500)
    assert prepared[0]["role"] == "system"
    assert len(prepared) < len(messages)
    assert audit is not None


def test_prepare_messages_never_splits_tool_call_and_result_pair():
    messages = [
        {"role": "system", "content": "contract"},
        {"role": "assistant", "tool_calls": [{"id": "call-1", "function": {"name": "tool"}}]},
        {"role": "tool", "tool_call_id": "call-1", "content": "x" * 600},
        {"role": "user", "content": "当前目标"},
    ]

    prepared, audit = prepare_messages(messages, budget=800)

    roles = [message["role"] for message in prepared]
    assert roles == ["system", "user"]
    assert audit is not None


def test_unified_budget_counts_schema_results_images_and_output_reserve():
    request = {
        "messages": [
            {"role": "system", "content": "硬约束"},
            {"role": "tool", "content": '{"reference":"平台规则","result":"完成"}'},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "发布这些图片"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + "x" * 10_000}},
                ],
            },
        ],
        "tools": [{"type": "function", "function": {"name": "publish", "parameters": {"type": "object"}}}],
    }

    prepared, audit = prepare_openai_context(
        request,
        policy=ContextBudgetPolicy(
            max_input_tokens=20_000,
            output_reserve_tokens=2_000,
            image_tokens=1_500,
        ),
    )

    assert prepared == request["messages"]
    assert audit["method"] == "utf8_bytes_upper_bound"
    assert audit["categories"]["images"] == 1_500
    assert audit["categories"]["output_reserve"] == 2_000
    assert audit["categories"]["schemas"] > 0
    assert audit["categories"]["messages"] > 0
    assert audit["total_tokens"] < 20_000


def test_unified_budget_compacts_old_facts_but_preserves_required_schema():
    request = {
        "messages": [
            {"role": "system", "content": "contract"},
            {"role": "user", "content": "current goal"},
            {
                "role": "assistant",
                "tool_calls": [{"id": "old", "function": {"name": "publish"}}],
            },
            {"role": "tool", "tool_call_id": "old", "content": "x" * 500},
            {
                "role": "assistant",
                "tool_calls": [{"id": "new", "function": {"name": "publish"}}],
            },
            {"role": "tool", "tool_call_id": "new", "content": "latest"},
        ],
        "tools": [{"type": "function", "function": {"name": "publish", "parameters": {"type": "object"}}}],
    }
    prepared, audit = prepare_openai_context(
        request,
        policy=ContextBudgetPolicy(max_input_tokens=700, output_reserve_tokens=100),
    )

    assert [item["role"] for item in prepared] == [
        "system",
        "user",
        "assistant",
        "tool",
    ]
    assert prepared[1]["content"] == "current goal"
    assert prepared[-1]["tool_call_id"] == "new"
    assert audit["compaction"] is not None
    assert request["tools"][0]["function"]["parameters"] == {"type": "object"}


def test_unified_budget_rejects_single_required_schema_instead_of_truncating():
    request = {
        "messages": [{"role": "system", "content": "contract"}],
        "tools": [{"type": "function", "function": {"parameters": {"description": "x" * 2_000}}}],
    }

    with pytest.raises(ContextBudgetError, match="Schema"):
        prepare_openai_context(
            request,
            policy=ContextBudgetPolicy(max_input_tokens=1_000, output_reserve_tokens=100),
        )


def test_unified_budget_uses_request_output_limit_and_provider_tokenizer():
    calls: list[str] = []

    def count_tokens(value: str) -> int:
        calls.append(value)
        return len(value.split()) + 1

    _prepared, audit = prepare_openai_context(
        {
            "messages": [
                {"role": "system", "content": "hard contract"},
                {"role": "user", "content": "current task"},
            ],
            "tools": [],
            "max_tokens": 321,
        },
        policy=ContextBudgetPolicy(max_input_tokens=1_000, output_reserve_tokens=100),
        token_counter=count_tokens,
    )

    assert calls
    assert audit["method"] == "provider_tokenizer"
    assert audit["categories"]["output_reserve"] == 321
