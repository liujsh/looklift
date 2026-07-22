"""图库扫描任务：后台执行、进度轮询与协作式取消。"""
from __future__ import annotations

import threading
import uuid
from dataclasses import asdict
from typing import Any

from .library_store import LibraryStore, ScanCancelled

_lock = threading.Lock()
_tasks: dict[str, dict[str, Any]] = {}
_cancellations: dict[str, threading.Event] = {}
_active_roots: dict[str, str] = {}


def submit(root_id: str) -> str:
    """验证索引根后启动扫描，立即返回任务 ID。"""
    store = LibraryStore()
    if all(root.id != root_id for root in store.list_roots()):
        raise KeyError(root_id)
    with _lock:
        active = _active_roots.get(root_id)
        if active is not None:
            return active
        task_id = uuid.uuid4().hex
        cancellation = threading.Event()
        _tasks[task_id] = _state("running", "准备扫描", scanned=0, current=None)
        _cancellations[task_id] = cancellation
        _active_roots[root_id] = task_id

    def progress(scanned: int, current: str) -> None:
        with _lock:
            _tasks[task_id] = _state(
                "running", f"已扫描 {scanned} 个文件", scanned=scanned, current=current
            )

    def run() -> None:
        try:
            result = store.scan_root(root_id, cancel_event=cancellation, progress=progress)
        except ScanCancelled:
            with _lock:
                previous = _tasks[task_id]
                _tasks[task_id] = _state(
                    "cancelled", "扫描已取消", scanned=previous["scanned"], current=previous["current"]
                )
        except Exception as exc:  # noqa: BLE001 —— 后台线程异常必须进入可观察任务态
            message = "图库扫描失败，请检查目录是否仍可访问" if isinstance(exc, OSError) else str(exc)
            with _lock:
                previous = _tasks[task_id]
                _tasks[task_id] = _state(
                    "error", None, error=message, scanned=previous["scanned"], current=previous["current"]
                )
        else:
            with _lock:
                previous = _tasks[task_id]
                _tasks[task_id] = _state(
                    "done", None, result=asdict(result), scanned=previous["scanned"], current=None
                )
        finally:
            with _lock:
                _cancellations.pop(task_id, None)
                if _active_roots.get(root_id) == task_id:
                    _active_roots.pop(root_id, None)

    threading.Thread(target=run, daemon=True, name=f"looklift-library-{task_id[:8]}").start()
    return task_id


def get(task_id: str) -> dict[str, Any] | None:
    with _lock:
        task = _tasks.get(task_id)
        return dict(task) if task is not None else None


def cancel(task_id: str) -> bool:
    with _lock:
        cancellation = _cancellations.get(task_id)
        if cancellation is None:
            return False
        cancellation.set()
        return True


def _state(
    status: str,
    message: str | None,
    *,
    result: dict | None = None,
    error: str | None = None,
    scanned: int,
    current: str | None,
) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "result": result,
        "error": error,
        "scanned": scanned,
        "current": current,
    }
