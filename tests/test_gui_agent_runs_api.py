from __future__ import annotations

import json

from looklift import config
from looklift.gui import api
from looklift.run_manifest import RunManifestRepository, hash_text
from looklift.session_store import SessionStore


def _ctx(*, run_id="run-a", body=None):
    return {
        "params": {"id": run_id},
        "body": json.dumps(body).encode() if body is not None else None,
        "content_type": "application/json",
        "query": {},
    }


def test_agent_run_recovery_api_lists_details_and_starts_new_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.toml")
    session = SessionStore().create_or_resume(
        str(tmp_path / "photo.jpg"),
        {"summary": "initial"},
    )
    repository = RunManifestRepository(config.run_manifest_dir())
    manifest = repository.create(
        "run-a",
        baseline_hash=hash_text(session.current_version_id),
        photo_hash=hash_text("photo"),
        attempt_id="attempt-1",
        runtime_id="openai-api",
        session_id=session.id,
        context_sources=({"id": "rule-natural", "version": 2, "hash": "a" * 64, "status": "used"},),
    )
    repository.store("run-a").reconcile(manifest, baseline_hash=manifest.baseline_hash)

    status, listed = api.ROUTES[("GET", "/api/agent/runs/recoverable")]({})
    assert status == 200
    assert listed["runs"][0]["status"] == "interrupted"

    status, detail = api.ROUTES[("GET", "/api/agent/runs/<id>")](_ctx())
    assert status == 200
    assert detail["run_id"] == "run-a"
    assert detail["context_sources"][0]["id"] == "rule-natural"

    status, resumed = api.ROUTES[("POST", "/api/agent/runs/<id>/resume")](
        _ctx(body={"attempt_id": "attempt-2", "runtime_id": "pi-cli"})
    )
    assert status == 202
    assert resumed["attempt_id"] == "attempt-2"
    assert resumed["status"] == "starting"


def test_agent_resume_uses_server_session_baseline_not_request_value(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.toml")
    session_store = SessionStore()
    session = session_store.create_or_resume(
        str(tmp_path / "photo.jpg"),
        {"summary": "initial"},
    )
    repository = RunManifestRepository(config.run_manifest_dir())
    manifest = repository.create(
        "run-stale",
        baseline_hash=hash_text(session.current_version_id),
        photo_hash=hash_text("photo"),
        attempt_id="attempt-1",
        session_id=session.id,
    )
    repository.store("run-stale").reconcile(
        manifest,
        baseline_hash=manifest.baseline_hash,
    )
    session_store.commit_exchange(
        session.id,
        [
            {"role": "user", "content": "修改", "provider": "fake", "status": "done"},
            {"role": "assistant", "content": "完成", "provider": "fake", "status": "done"},
        ],
        {"summary": "changed"},
        "chat",
    )

    status, body = api.ROUTES[("POST", "/api/agent/runs/<id>/resume")](
        _ctx(
            run_id="run-stale",
            body={
                "attempt_id": "attempt-2",
                "baseline_hash": manifest.baseline_hash,
            },
        )
    )
    assert status == 409
    assert "基线" in body["error"]
    assert repository.load("run-stale").status == "stale"
