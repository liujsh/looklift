from looklift.context_memory import ContextEntry, ContextMemoryStore
from looklift.memory_gate import MemoryCandidate, MemoryGate


def test_gate_accepts_stable_preference_without_user_confirmation():
    decision = MemoryGate().evaluate(
        MemoryCandidate("pref-cool", "preference", "偏好低饱和冷色调", "auto:chat")
    )
    assert decision.action == "write"
    assert decision.reason == "gate-accepted"


def test_gate_rejects_sensitive_content():
    decision = MemoryGate().evaluate(
        MemoryCandidate("secret", "fact", "api_key=sk-secret", "auto:chat")
    )
    assert decision.action == "skip"
    assert decision.reason == "sensitive-content"


def test_gate_requires_scope_identity():
    gate = MemoryGate()
    assert gate.evaluate(MemoryCandidate("p", "project", "客户偏好", "auto", scope="project")).reason == "project-id-required"
    assert gate.evaluate(MemoryCandidate("r", "fact", "临时要求", "auto", scope="run")).reason == "run-lifecycle-required"


def test_gate_deduplicates_existing_entry():
    existing = ContextEntry("pref-cool", "preference", "偏好低饱和冷色调", "user", state="active")
    decision = MemoryGate().evaluate(
        MemoryCandidate("new-id", "preference", "  偏好低饱和冷色调 ", "auto"), [existing]
    )
    assert decision.action == "merge"
    assert decision.duplicate_id == "pref-cool"


def test_store_auto_put_uses_gate(tmp_path):
    store = ContextMemoryStore(tmp_path)
    result = store.auto_put(
        MemoryCandidate("pref-cool", "preference", "偏好低饱和冷色调", "auto:chat")
    )
    assert result is not None
    assert result.state == "active"
    assert result.source == "auto:chat"
