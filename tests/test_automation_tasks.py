from __future__ import annotations

import threading
import time
from pathlib import Path

from looklift.automation_store import AutomationStore
from looklift.automation_tasks import AutomationTaskManager


def _workflow_and_plan(tmp_path, sample_analysis, count=3):
    sources = []
    for index in range(count):
        source = tmp_path / f"照片-{index}.jpg"
        source.write_bytes(b"jpeg")
        sources.append(str(source))
    output = tmp_path / "输出"
    output.mkdir()
    store = AutomationStore(tmp_path / "automation")
    workflow = store.create_workflow(
        name="批量",
        look_name="柔和胶片",
        factor=0.8,
        suffix="-done",
        quality=90,
    )
    return store, store.create_plan(workflow, sample_analysis, sources, str(output))


def _wait(manager: AutomationTaskManager, task_id: str) -> dict:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        state = manager.get_run(task_id)
        if state["status"] != "running":
            return state
        time.sleep(0.01)
    raise AssertionError("任务未结束")


def test_run_isolates_failure_and_retry_only_failed_items(tmp_path, sample_analysis):
    store, plan = _workflow_and_plan(tmp_path, sample_analysis)
    attempts: dict[str, int] = {}

    def render(source: Path, output: Path, analysis: dict, factor: float, quality: int):
        attempts[source.name] = attempts.get(source.name, 0) + 1
        if source.name == "照片-1.jpg" and attempts[source.name] == 1:
            raise RuntimeError("模拟损坏")
        output.write_bytes(f"{factor}:{quality}".encode())

    manager = AutomationTaskManager(store, renderer=render)
    first = _wait(manager, manager.start(plan["id"]))

    assert first["status"] == "done"
    assert first["completed"] == 2
    assert first["failed"] == 1
    assert [item["status"] for item in first["items"]] == ["completed", "failed", "completed"]

    retried = _wait(manager, manager.retry(first["id"]))
    assert retried["completed"] == 3
    assert retried["failed"] == 0
    assert attempts == {"照片-0.jpg": 1, "照片-1.jpg": 2, "照片-2.jpg": 1}

    restored = AutomationTaskManager(store, renderer=render).get_run(first["id"])
    assert restored["completed"] == 3


def test_cancel_keeps_completed_and_does_not_start_remaining(tmp_path, sample_analysis):
    store, plan = _workflow_and_plan(tmp_path, sample_analysis)
    first_started = threading.Event()
    release = threading.Event()
    rendered: list[str] = []

    def render(source: Path, output: Path, analysis: dict, factor: float, quality: int):
        rendered.append(source.name)
        first_started.set()
        release.wait(2)
        output.write_bytes(b"ok")

    manager = AutomationTaskManager(store, renderer=render)
    task_id = manager.start(plan["id"])
    assert first_started.wait(1)
    assert manager.cancel(task_id) is True
    release.set()
    result = _wait(manager, task_id)

    assert result["status"] == "cancelled"
    assert rendered == ["照片-0.jpg"]
    assert [item["status"] for item in result["items"]] == ["completed", "cancelled", "cancelled"]


def test_stale_running_manifest_becomes_interrupted(tmp_path, sample_analysis):
    store, plan = _workflow_and_plan(tmp_path, sample_analysis, count=1)
    run = {
        "id": "stale",
        "plan_id": plan["id"],
        "workflow": plan["workflow"],
        "analysis": plan["analysis"],
        "status": "running",
        "created_at": plan["created_at"],
        "updated_at": plan["created_at"],
        "items": [{**plan["items"][0], "status": "running", "error": None}],
    }
    store.save_run(run)

    restored = AutomationTaskManager(store, renderer=lambda *_: None).get_run("stale")

    assert restored["status"] == "interrupted"
    assert restored["items"][0]["status"] == "interrupted"
