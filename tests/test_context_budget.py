from looklift.context_budget import prepare_messages


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
