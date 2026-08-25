from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from looklift.context_memory import ContextEntry, ContextMemoryStore
from looklift.proposal import ProposalError, ProposalService


def test_context_store_restart_restores_entries_config_and_confirmed_snapshot(tmp_path):
    store = ContextMemoryStore(tmp_path)
    store.put(ContextEntry("rule-natural", "rule", "禁止过度锐化", "user", confirmed=True))
    store.put(ContextEntry("fact-draft", "fact", "尚未确认", "agent"))
    store.update_config(auto_extract=True)

    restored = ContextMemoryStore(tmp_path)

    assert restored.get("rule-natural").content == "禁止过度锐化"
    assert restored.config()["auto_extract"] is True
    assert [entry.entry_id for entry in restored.snapshot()] == ["rule-natural"]
    assert (tmp_path / "index.json").is_file()


@pytest.mark.parametrize("entry_id", ["../secret", "a/b", "a\\b", ".", "含 空格"])
def test_context_store_rejects_unsafe_entry_ids(tmp_path, entry_id):
    store = ContextMemoryStore(tmp_path)

    with pytest.raises(ValueError, match="ID"):
        store.put(ContextEntry(entry_id, "fact", "内容", "user", confirmed=True))

    assert list(tmp_path.glob("*.md")) == []


def test_disable_creates_new_version_and_keeps_historical_file_auditable(tmp_path):
    store = ContextMemoryStore(tmp_path)
    original = store.put(ContextEntry("preference-warm", "preference", "偏暖", "user", confirmed=True))

    disabled = store.disable(original.entry_id)

    assert disabled.enabled is False
    assert disabled.version == 2
    assert store.snapshot() == ()
    assert (tmp_path / "preference-warm.md").read_text(encoding="utf-8").find("偏暖") >= 0


def test_snapshot_redacts_paths_keys_and_exif_without_rewriting_source(tmp_path):
    store = ContextMemoryStore(tmp_path)
    content = "原图 C:\\Users\\name\\photo.raw\napi_key=sk-secret-value\nEXIF: GPS=31,121\n保持自然"
    store.put(ContextEntry("project-private", "project", content, "user", confirmed=True))

    snapshot = store.snapshot()[0]

    assert "C:\\Users" not in snapshot.content
    assert "sk-secret" not in snapshot.content
    assert "GPS" not in snapshot.content
    assert snapshot.content.count("[已脱敏]") == 3
    assert store.get("project-private").content == content


def test_persistent_proposal_lifecycle_is_idempotent_and_detects_conflict(tmp_path):
    now = datetime(2026, 8, 25, tzinfo=timezone.utc)
    service = ProposalService(path=tmp_path / "proposals.json", clock=lambda: now)
    proposal = service.preview(
        target_type="Memory",
        target_id="fact-a",
        base_hash="a" * 64,
        patch={"content": "更新"},
        source_packet_ids=("packet-a",),
    )

    assert service.confirm(proposal.proposal_id) == service.confirm(proposal.proposal_id)
    restored = ProposalService(path=tmp_path / "proposals.json", clock=lambda: now)
    conflict = restored.apply(
        proposal.proposal_id,
        current_hash="b" * 64,
        apply_target=lambda _: "never",
    )
    assert conflict.status == "conflict"
    assert restored.apply(
        proposal.proposal_id,
        current_hash="b" * 64,
        apply_target=lambda _: "never",
    ) == conflict


def test_expired_proposal_cannot_be_confirmed_after_restart(tmp_path):
    current = datetime(2026, 8, 25, tzinfo=timezone.utc)
    service = ProposalService(path=tmp_path / "proposals.json", clock=lambda: current)
    proposal = service.preview(
        target_type="Memory",
        target_id="fact-a",
        base_hash="a" * 64,
        patch={"content": "更新"},
        ttl=timedelta(seconds=1),
    )
    current += timedelta(seconds=2)

    with pytest.raises(ProposalError, match="preview"):
        ProposalService(path=tmp_path / "proposals.json", clock=lambda: current).confirm(proposal.proposal_id)
