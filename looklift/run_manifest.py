"""可审计 Run Manifest：追加事实、启动收敛与 Attempt 恢复。"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any


class ManifestError(ValueError):
    pass


@dataclass(frozen=True)
class RunManifest:
    run_id: str
    status: str
    baseline_hash: str
    photo_hash: str
    attempt_id: str | None = None
    last_sequence: int = 0
    last_candidate_revision: str | None = None
    stale_reason: str | None = None


class RunManifestStore:
    """JSONL 事实日志；快照原子替换，损坏尾记录可截断。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def create(self, run_id: str, *, baseline_hash: str, photo_hash: str, attempt_id: str) -> RunManifest:
        if not run_id or len(baseline_hash) != 64 or len(photo_hash) != 64:
            raise ManifestError("Manifest 身份或 Hash 无效")
        manifest = RunManifest(run_id, "starting", baseline_hash, photo_hash, attempt_id)
        self._write_snapshot(manifest)
        return manifest

    def load(self) -> RunManifest:
        snapshot = self.path.with_suffix(".snapshot.json")
        if not snapshot.exists():
            raise ManifestError("Manifest 不存在")
        try:
            return RunManifest(**json.loads(snapshot.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError) as exc:
            raise ManifestError("Manifest 快照损坏") from exc

    def append(self, manifest: RunManifest, *, event_id: str, sequence: int,
               kind: str, payload: dict[str, Any]) -> RunManifest:
        if sequence <= manifest.last_sequence:
            return manifest
        event = {"event_id": event_id, "sequence": sequence, "kind": kind, "payload": payload}
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        next_manifest = self._reduce(manifest, kind, sequence, payload)
        self._write_snapshot(next_manifest)
        return next_manifest

    def reconcile(self, manifest: RunManifest, *, baseline_hash: str) -> RunManifest:
        if manifest.status in {"starting", "running", "cancelling"}:
            manifest = replace(manifest, status="interrupted")
        if baseline_hash != manifest.baseline_hash:
            manifest = replace(manifest, status="stale", stale_reason="正式基线已变化")
        self._write_snapshot(manifest)
        return manifest

    def start_attempt(self, manifest: RunManifest, attempt_id: str) -> RunManifest:
        if manifest.status == "stale":
            raise ManifestError("stale 运行不能直接恢复")
        next_manifest = replace(manifest, attempt_id=attempt_id, status="starting")
        self._write_snapshot(next_manifest)
        return next_manifest

    def _reduce(self, manifest: RunManifest, kind: str, sequence: int, payload: dict[str, Any]) -> RunManifest:
        status = manifest.status
        revision = manifest.last_candidate_revision
        if kind == "run_started": status = "running"
        elif kind == "candidate_created": revision = payload.get("revision") or revision
        elif kind == "run_finished": status = "completed"
        elif kind == "run_failed": status = "failed"
        return replace(manifest, status=status, last_sequence=sequence, last_candidate_revision=revision)

    def _write_snapshot(self, manifest: RunManifest) -> None:
        target = self.path.with_suffix(".snapshot.json")
        fd, temporary = tempfile.mkstemp(prefix="manifest-", suffix=".json", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(manifest.__dict__, handle, ensure_ascii=False, sort_keys=True)
                handle.flush(); os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary): os.unlink(temporary)


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
