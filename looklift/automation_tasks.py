"""自动化成片后台任务、持久化进度、取消与失败重试。"""
from __future__ import annotations

import copy
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .automation_render import render_automation_jpeg
from .automation_store import AutomationStore

Renderer = Callable[[Path, Path, dict, float, int], None]
_RETRYABLE = {"failed", "interrupted", "cancelled"}


class AutomationTaskManager:
    """一个进程内协调线程，运行清单由 AutomationStore 持久化。"""

    def __init__(
        self,
        store: AutomationStore | None = None,
        *,
        renderer: Renderer = render_automation_jpeg,
    ):
        self.store = store or AutomationStore()
        self.renderer = renderer
        self._lock = threading.Lock()
        self._active: set[str] = set()
        self._cancellations: dict[str, threading.Event] = {}

    def start(self, plan_id: str) -> str:
        plan = self.store.get_plan(plan_id)
        if plan is None:
            raise KeyError(plan_id)
        if not plan.get("ready"):
            raise ValueError("执行计划仍有无效输入或输出冲突")
        run_id = uuid.uuid4().hex
        now = _now()
        run = {
            "id": run_id,
            "plan_id": plan_id,
            "workflow": copy.deepcopy(plan["workflow"]),
            "analysis": copy.deepcopy(plan["analysis"]),
            "status": "running",
            "created_at": now,
            "updated_at": now,
            "items": [
                {**copy.deepcopy(item), "status": "pending", "error": None}
                for item in plan["items"]
            ],
        }
        self.store.save_run(run)
        self._launch(run_id)
        return run_id

    def get_run(self, run_id: str) -> dict[str, Any]:
        run = self.store.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        with self._lock:
            active = run_id in self._active
        if run["status"] == "running" and not active:
            run["status"] = "interrupted"
            for item in run["items"]:
                if item["status"] in {"running", "pending"}:
                    item["status"] = "interrupted"
                    item["error"] = "上次运行意外中断"
            run["updated_at"] = _now()
            self.store.save_run(run)
        return _with_counts(run)

    def list_runs(self) -> list[dict[str, Any]]:
        return [self.get_run(run["id"]) for run in self.store.list_runs()]

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            cancellation = self._cancellations.get(run_id)
            if cancellation is None:
                return False
            cancellation.set()
            return True

    def retry(self, run_id: str) -> str:
        run = self.get_run(run_id)
        with self._lock:
            if run_id in self._active:
                raise ValueError("自动化任务仍在运行")
        retryable = [item for item in run["items"] if item["status"] in _RETRYABLE]
        if not retryable:
            raise ValueError("没有可重试的失败或中断项目")
        for item in retryable:
            item["status"] = "pending"
            item["error"] = None
        run["status"] = "running"
        run["updated_at"] = _now()
        run.pop("completed", None)
        run.pop("failed", None)
        run.pop("cancelled", None)
        self.store.save_run(run)
        self._launch(run_id)
        return run_id

    def _launch(self, run_id: str) -> None:
        cancellation = threading.Event()
        with self._lock:
            self._active.add(run_id)
            self._cancellations[run_id] = cancellation
        threading.Thread(
            target=self._run,
            args=(run_id, cancellation),
            daemon=True,
            name=f"looklift-automation-{run_id[:8]}",
        ).start()

    def _run(self, run_id: str, cancellation: threading.Event) -> None:
        try:
            run = self.store.get_run(run_id)
            if run is None:
                return
            for index, item in enumerate(run["items"]):
                if item["status"] != "pending":
                    continue
                if cancellation.is_set():
                    for remaining in run["items"][index:]:
                        if remaining["status"] == "pending":
                            remaining["status"] = "cancelled"
                            remaining["error"] = "用户取消"
                    run["status"] = "cancelled"
                    run["updated_at"] = _now()
                    self.store.save_run(run)
                    break
                item["status"] = "running"
                run["updated_at"] = _now()
                self.store.save_run(run)
                try:
                    output = Path(item["output"])
                    if output.exists():
                        raise FileExistsError(f"输出文件已存在：{output}")
                    self.renderer(
                        Path(item["source"]),
                        output,
                        run["analysis"],
                        run["workflow"]["factor"],
                        run["workflow"]["quality"],
                    )
                except Exception as exc:  # noqa: BLE001 —— 单张失败必须隔离并记录
                    item["status"] = "failed"
                    item["error"] = str(exc) or exc.__class__.__name__
                else:
                    item["status"] = "completed"
                    item["error"] = None
                run["updated_at"] = _now()
                self.store.save_run(run)
            else:
                run["status"] = "done"
                run["updated_at"] = _now()
                self.store.save_run(run)
        finally:
            with self._lock:
                self._active.discard(run_id)
                self._cancellations.pop(run_id, None)


def _with_counts(run: dict[str, Any]) -> dict[str, Any]:
    public = copy.deepcopy(run)
    statuses = [item["status"] for item in public["items"]]
    public["completed"] = statuses.count("completed")
    public["failed"] = statuses.count("failed")
    public["cancelled"] = statuses.count("cancelled")
    public["total"] = len(statuses)
    return public


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
