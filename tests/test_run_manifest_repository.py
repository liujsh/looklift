from __future__ import annotations

import pytest
import json

from looklift.run_manifest import (
    ManifestError,
    RunManifestRepository,
    hash_text,
)


def test_repository_lists_recoverable_runs_and_reconciles_startup(tmp_path):
    repository = RunManifestRepository(tmp_path)
    first = repository.create(
        "run-a",
        baseline_hash=hash_text("baseline"),
        photo_hash=hash_text("photo"),
        attempt_id="attempt-1",
        runtime_id="pydantic-api",
        provider="anthropic",
        model="claude-test",
    )
    first = repository.store("run-a").append(
        first,
        event_id="e1",
        sequence=1,
        kind="run_started",
        payload={},
    )
    assert first.status == "running"
    reconciled = repository.reconcile_startup()
    assert reconciled[0].status == "interrupted"
    assert repository.list_recoverable()[0].run_id == "run-a"


def test_resume_creates_new_attempt_without_reusing_sequence(tmp_path):
    repository = RunManifestRepository(tmp_path)
    manifest = repository.create(
        "run-a",
        baseline_hash=hash_text("baseline"),
        photo_hash=hash_text("photo"),
        attempt_id="attempt-1",
    )
    manifest = repository.store("run-a").reconcile(
        manifest,
        baseline_hash=manifest.baseline_hash,
    )
    resumed = repository.start_attempt(
        "run-a",
        attempt_id="attempt-2",
        baseline_hash=manifest.baseline_hash,
        runtime_id="pi-cli",
    )
    assert resumed.attempt_id == "attempt-2"
    assert resumed.runtime_id == "pi-cli"
    assert resumed.status == "starting"
    assert resumed.last_sequence == 0


def test_resume_rejects_stale_baseline_and_unsafe_run_id(tmp_path):
    repository = RunManifestRepository(tmp_path)
    repository.create(
        "run-a",
        baseline_hash=hash_text("baseline"),
        photo_hash=hash_text("photo"),
        attempt_id="attempt-1",
    )
    with pytest.raises(ManifestError, match="基线"):
        repository.start_attempt(
            "run-a",
            attempt_id="attempt-2",
            baseline_hash=hash_text("changed"),
        )
    with pytest.raises(ManifestError, match="ID"):
        repository.store("../escape")


def test_completed_run_cannot_be_resumed(tmp_path):
    repository = RunManifestRepository(tmp_path)
    manifest = repository.create(
        "run-a",
        baseline_hash=hash_text("baseline"),
        photo_hash=hash_text("photo"),
        attempt_id="attempt-1",
    )
    manifest = repository.store("run-a").append(
        manifest,
        event_id="e1",
        sequence=1,
        kind="run_finished",
        payload={},
    )
    with pytest.raises(ManifestError, match="中断或失败"):
        repository.start_attempt(
            "run-a",
            attempt_id="attempt-2",
            baseline_hash=manifest.baseline_hash,
        )


def test_manifest_persists_redacted_context_source_summary(tmp_path):
    repository = RunManifestRepository(tmp_path)
    sources = (
        {"id": "rule-natural", "version": 2, "hash": "a" * 64, "status": "used"},
        {"id": "reference-catalog", "version": 1, "hash": "b" * 64, "status": "omitted", "reason": "预算不足"},
    )
    repository.create(
        "run-context",
        baseline_hash=hash_text("baseline"),
        photo_hash=hash_text("photo"),
        attempt_id="attempt-1",
        context_sources=sources,
    )

    restored = repository.load("run-context")

    assert restored.context_sources == sources
    assert "C:\\" not in json.dumps(restored.context_sources, ensure_ascii=False)
