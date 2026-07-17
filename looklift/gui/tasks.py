"""长任务表：后台线程 + 内存态任务记录，轮询查询状态/结果。"""
from __future__ import annotations

import threading
import uuid
from typing import Any, Callable

_lock = threading.Lock()
_tasks: dict[str, dict[str, Any]] = {}


def submit(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> str:
    """在后台守护线程里跑 `fn(*args, **kwargs)`，立即返回 task_id 供轮询。

    任务态形状（design.md 决策 2）：`{status, message, result, error}`。
    `status`：`running` → `done`（带 `result`）或 `error`（`error` 是
    `str(exc)`，中文异常信息原样透传）。`message` 运行中固定「运行中」，
    结束后（done/error）为 `None`——字段本身始终存在，值是否为 `None` 由
    调用方按需展示。
    """
    task_id = uuid.uuid4().hex
    with _lock:
        _tasks[task_id] = {"status": "running", "message": "运行中", "result": None, "error": None}

    def _run() -> None:
        try:
            result = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 —— 任意异常都要落进任务态，不能让后台线程静默崩溃
            with _lock:
                _tasks[task_id] = {"status": "error", "message": None, "result": None, "error": str(exc)}
        else:
            with _lock:
                _tasks[task_id] = {"status": "done", "message": None, "result": result, "error": None}

    threading.Thread(target=_run, daemon=True).start()
    return task_id


def get(task_id: str) -> dict[str, Any] | None:
    """查询任务当前态；`task_id` 不存在时返回 `None`。"""
    with _lock:
        task = _tasks.get(task_id)
        return dict(task) if task is not None else None
