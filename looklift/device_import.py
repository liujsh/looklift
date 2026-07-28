"""v2.3-B 设备照片发现与安全导入。"""
from __future__ import annotations

import hashlib
import os
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from . import config, library_tasks
from .library_store import LibraryStore

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".dng", ".nef", ".cr2", ".cr3", ".arw", ".raf", ".rw2"}
_lock = threading.Lock()
_tasks: dict[str, dict[str, Any]] = {}
_cancel: dict[str, threading.Event] = {}


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sources() -> list[dict[str, str]]:
    injected = os.environ.get("LOOKLIFT_IMPORT_SOURCES", "")
    paths = [Path(p) for p in injected.split(";") if p.strip()] if injected else []
    if not paths and os.name == "nt":
        paths = [Path(f"{chr(c)}:/") for c in range(ord("A"), ord("Z") + 1) if Path(f"{chr(c)}:/").exists()]
    if not paths:
        paths = [Path(p) for p in ("/media", "/mnt") if Path(p).is_dir()]
    result = []
    for path in paths:
        try:
            resolved = path.resolve()
            if resolved.is_dir():
                result.append({"id": str(resolved), "name": resolved.name or str(resolved), "path": str(resolved), "kind": "device"})
        except OSError:
            continue
    return result


def manifest(source_id: str, date: str = "", unimported: bool = False) -> list[dict[str, Any]]:
    source = next((item for item in sources() if item["id"] == source_id), None)
    if source is None:
        raise KeyError(source_id)
    imported = _indexed_hashes()
    result = []
    for path in Path(source["path"]).rglob("*"):
        if not path.is_file() or path.suffix.lower() not in EXTENSIONS:
            continue
        stat = path.stat()
        modified = datetime.fromtimestamp(stat.st_mtime).date().isoformat()
        if date and modified != date:
            continue
        digest = _hash(path)
        duplicate = digest in imported
        if unimported and duplicate:
            continue
        result.append({"path": str(path), "name": path.name, "size": stat.st_size, "modified": modified, "format": path.suffix[1:].upper(), "fingerprint": digest, "duplicate": duplicate})
    return sorted(result, key=lambda item: (item["modified"], item["name"].casefold()))


def _indexed_hashes() -> set[str]:
    hashes: set[str] = set()
    for root in LibraryStore().list_roots():
        for path in Path(root.path).rglob("*"):
            if path.is_file() and path.suffix.lower() in EXTENSIONS:
                try:
                    hashes.add(_hash(path))
                except OSError:
                    pass
    return hashes


def start(paths: list[str], target: str | None = None) -> str:
    if not paths:
        raise ValueError("至少选择一张照片")
    target_path = Path(target or (config.library_db_path().parent / "imports")).expanduser().resolve()
    target_path.mkdir(parents=True, exist_ok=True)
    task_id = uuid.uuid4().hex
    event = threading.Event()
    with _lock:
        _tasks[task_id] = {"status": "running", "message": "准备导入", "total": len(paths), "completed": 0, "skipped": 0, "failed": [], "paths": []}
        _cancel[task_id] = event

    def run() -> None:
        state = _tasks[task_id]
        try:
            known = _indexed_hashes()
            for source_name in paths:
                if event.is_set():
                    state["status"] = "cancelled"; state["message"] = "导入已取消"; break
                source = Path(source_name)
                if not source.is_file():
                    state["failed"].append({"path": source_name, "error": "文件不存在"}); continue
                digest = _hash(source)
                if digest in known:
                    state["skipped"] += 1; continue
                destination = target_path / source.name
                if destination.exists(): destination = target_path / f"{source.stem}-{digest[:8]}{source.suffix}"
                temporary = target_path / f".looklift-import-{uuid.uuid4().hex}.tmp"
                try:
                    shutil.copyfile(source, temporary)
                    if temporary.stat().st_size != source.stat().st_size or _hash(temporary) != digest:
                        raise IOError("导入校验失败")
                    os.replace(temporary, destination)
                    known.add(digest); state["paths"].append(str(destination))
                except Exception as exc:  # noqa: BLE001
                    state["failed"].append({"path": source_name, "error": str(exc)})
                    if temporary.exists(): temporary.unlink(missing_ok=True)
                state["completed"] += 1
            if state["status"] == "running": state["status"] = "done"; state["message"] = "导入完成"
            store = LibraryStore()
            try:
                root = store.add_root(target_path)
            except ValueError:
                root = next((item for item in store.list_roots() if target_path == Path(item.path) or target_path.is_relative_to(Path(item.path))), None)
            if root is not None:
                state["scan_task_id"] = library_tasks.submit(root.id)
        except Exception as exc: state["status"] = "error"; state["message"] = str(exc)
        finally:
            with _lock: _cancel.pop(task_id, None)
    threading.Thread(target=run, daemon=True, name=f"looklift-import-{task_id[:8]}").start()
    return task_id


def get(task_id: str) -> dict[str, Any] | None:
    with _lock: return dict(_tasks[task_id]) if task_id in _tasks else None


def cancel(task_id: str) -> bool:
    with _lock:
        event = _cancel.get(task_id)
        if event is None: return False
        event.set(); return True
