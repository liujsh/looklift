import threading
import time
from types import SimpleNamespace

from looklift import library_tasks
from looklift.library_store import ScanCancelled, ScanResult


def _wait_for_terminal(task_id: str) -> dict:
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        task = library_tasks.get(task_id)
        if task is not None and task["status"] != "running":
            return task
        time.sleep(0.01)
    raise AssertionError("图库任务未在预期时间内结束")


def test_same_root_reuses_running_scan_task(monkeypatch):
    started = threading.Event()
    release = threading.Event()

    class BlockingStore:
        def list_roots(self):
            return [SimpleNamespace(id="root")]

        def scan_root(self, _root_id, *, cancel_event, progress):
            progress(1, "a.jpg")
            started.set()
            release.wait(timeout=2)
            return ScanResult(1, 0, 0)

    monkeypatch.setattr(library_tasks, "LibraryStore", BlockingStore)

    first = library_tasks.submit("root")
    assert started.wait(timeout=1)
    second = library_tasks.submit("root")
    release.set()

    assert second == first
    assert _wait_for_terminal(first)["status"] == "done"


def test_cancel_signals_running_scan_and_preserves_cancelled_terminal_state(monkeypatch):
    started = threading.Event()

    class CancellableStore:
        def list_roots(self):
            return [SimpleNamespace(id="cancel-root")]

        def scan_root(self, _root_id, *, cancel_event, progress):
            progress(1, "a.jpg")
            started.set()
            cancel_event.wait(timeout=2)
            raise ScanCancelled("已取消")

    monkeypatch.setattr(library_tasks, "LibraryStore", CancellableStore)
    task_id = library_tasks.submit("cancel-root")
    assert started.wait(timeout=1)

    assert library_tasks.cancel(task_id) is True
    task = _wait_for_terminal(task_id)

    assert task["status"] == "cancelled"
    assert task["scanned"] == 1
    assert library_tasks.cancel(task_id) is False
