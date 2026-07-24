from __future__ import annotations

import json
import time
from pathlib import Path

from looklift.automation_store import AutomationStore
from looklift.automation_tasks import AutomationTaskManager
from looklift.gui import api


def _call(method: str, pattern: str, payload=None, **params):
    body = None if payload is None else json.dumps(payload).encode()
    return api.ROUTES[(method, pattern)]({
        "params": params,
        "body": body,
        "query": {},
    })


def _wait(run_id: str):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        status, run = _call("GET", "/api/automation/runs/<id>", id=run_id)
        if run["status"] != "running":
            return status, run
        time.sleep(0.01)
    raise AssertionError("任务未完成")


def test_workflow_plan_run_and_delete_api(tmp_path, sample_analysis, monkeypatch):
    store = AutomationStore(tmp_path / "automation")
    manager = AutomationTaskManager(
        store,
        renderer=lambda source, output, analysis, factor, quality: output.write_bytes(b"jpg"),
    )
    monkeypatch.setattr(api, "_automation_components", lambda: (store, manager))
    monkeypatch.setattr(api.lookstore, "load", lambda looks_dir, name: sample_analysis if name == "柔和胶片" else None)
    source = tmp_path / "照片.jpg"
    source.write_bytes(b"source")
    output = tmp_path / "输出"
    output.mkdir()

    status, workflow = _call("POST", "/api/automation/workflows", {
        "name": "日常胶片",
        "look_name": "柔和胶片",
        "factor": 0.8,
        "suffix": "-film",
        "quality": 92,
    })
    assert status == 200
    assert _call("GET", "/api/automation/workflows") == (200, {"workflows": [workflow]})

    status, plan = _call("POST", "/api/automation/plans", {
        "workflow_id": workflow["id"],
        "inputs": [str(source)],
        "output_dir": str(output),
    })
    assert status == 200 and plan["ready"] is True
    assert "analysis" not in plan

    status, started = _call("POST", "/api/automation/runs", {"plan_id": plan["id"]})
    assert status == 202
    status, run = _wait(started["run_id"])
    assert status == 200 and run["completed"] == 1
    assert "analysis" not in run
    assert (output / "照片-film.jpg").read_bytes() == b"jpg"

    assert _call("DELETE", "/api/automation/workflows/<id>", id=workflow["id"]) == (200, {"ok": True})


def test_automation_api_rejects_missing_look_and_conflicted_plan(tmp_path, sample_analysis, monkeypatch):
    store = AutomationStore(tmp_path / "automation")
    manager = AutomationTaskManager(store, renderer=lambda *_: None)
    monkeypatch.setattr(api, "_automation_components", lambda: (store, manager))
    monkeypatch.setattr(api.lookstore, "load", lambda looks_dir, name: None)

    status, error = _call("POST", "/api/automation/workflows", {
        "name": "坏技能", "look_name": "不存在", "factor": 1, "suffix": "-x", "quality": 90,
    })
    assert status == 404 and "风格库" in error["error"]

    monkeypatch.setattr(api.lookstore, "load", lambda looks_dir, name: sample_analysis)
    _, workflow = _call("POST", "/api/automation/workflows", {
        "name": "冲突", "look_name": "青橙经典", "factor": 1, "suffix": "-x", "quality": 90,
    })
    source = tmp_path / "照片.jpg"
    source.write_bytes(b"source")
    output = tmp_path / "输出"
    output.mkdir()
    (output / "照片-x.jpg").write_bytes(b"existing")
    _, plan = _call("POST", "/api/automation/plans", {
        "workflow_id": workflow["id"], "inputs": [str(source)], "output_dir": str(output),
    })

    assert plan["ready"] is False
    status, error = _call("POST", "/api/automation/runs", {"plan_id": plan["id"]})
    assert status == 409 and "冲突" in error["error"]


def test_automation_retry_and_cancel_terminal_errors(tmp_path, sample_analysis, monkeypatch):
    store = AutomationStore(tmp_path / "automation")
    attempts = 0

    def fail_once(source: Path, output: Path, analysis: dict, factor: float, quality: int):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("一次失败")
        output.write_bytes(b"ok")

    manager = AutomationTaskManager(store, renderer=fail_once)
    monkeypatch.setattr(api, "_automation_components", lambda: (store, manager))
    monkeypatch.setattr(api.lookstore, "load", lambda looks_dir, name: sample_analysis)
    source = tmp_path / "照片.jpg"
    source.write_bytes(b"source")
    output = tmp_path / "输出"
    output.mkdir()
    _, workflow = _call("POST", "/api/automation/workflows", {
        "name": "重试", "look_name": "柔和胶片", "factor": 1, "suffix": "-x", "quality": 90,
    })
    _, plan = _call("POST", "/api/automation/plans", {
        "workflow_id": workflow["id"], "inputs": [str(source)], "output_dir": str(output),
    })
    _, started = _call("POST", "/api/automation/runs", {"plan_id": plan["id"]})
    _, failed = _wait(started["run_id"])
    assert failed["failed"] == 1

    assert _call("POST", "/api/automation/runs/<id>/retry", id=failed["id"]) == (
        202, {"run_id": failed["id"]},
    )
    _, retried = _wait(failed["id"])
    assert retried["completed"] == 1
    status, _ = _call("POST", "/api/automation/runs/<id>/cancel", id=failed["id"])
    assert status == 409
