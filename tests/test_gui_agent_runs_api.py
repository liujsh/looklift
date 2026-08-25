from __future__ import annotations

import json

from looklift import config
from looklift.gui import api
from looklift.run_manifest import RunManifestRepository, hash_text


def _ctx(*, run_id="run-a", body=None):
    return {
        "params": {"id": run_id},
        "body": json.dumps(body).encode() if body is not None else None,
        "content_type": "application/json",
        "query": {},
    }


def test_agent_run_recovery_api_lists_details_and_starts_new_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.toml")
    repository = RunManifestRepository(config.run_manifest_dir())
    manifest = repository.create(
        "run-a",
        baseline_hash=hash_text("baseline"),
        photo_hash=hash_text("photo"),
        attempt_id="attempt-1",
        runtime_id="pydantic-api",
    )
    repository.store("run-a").reconcile(manifest, baseline_hash=manifest.baseline_hash)

    status, listed = api.ROUTES[("GET", "/api/agent/runs/recoverable")]({})
    assert status == 200
    assert listed["runs"][0]["status"] == "interrupted"

    status, detail = api.ROUTES[("GET", "/api/agent/runs/<id>")](_ctx())
    assert status == 200
    assert detail["run_id"] == "run-a"

    status, resumed = api.ROUTES[("POST", "/api/agent/runs/<id>/resume")](
        _ctx(body={"attempt_id": "attempt-2", "baseline_hash": manifest.baseline_hash, "runtime_id": "pi-cli"})
    )
    assert status == 202
    assert resumed["attempt_id"] == "attempt-2"
    assert resumed["status"] == "starting"
