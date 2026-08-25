"""可审计 Run Manifest：追加事实、启动收敛与 Attempt 恢复。"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from .agent_adapter import AgentEvent


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
    runtime_id: str | None = None
    provider: str | None = None
    model: str | None = None
    domain_pack_hash: str | None = None


class RunManifestStore:
    """JSONL 事实日志；快照原子替换，损坏尾记录可截断。"""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def create(
        self,
        run_id: str,
        *,
        baseline_hash: str,
        photo_hash: str,
        attempt_id: str,
        runtime_id: str | None = None,
        provider: str | None = None,
        model: str | None = None,
        domain_pack_hash: str | None = None,
    ) -> RunManifest:
        if not run_id or len(baseline_hash) != 64 or len(photo_hash) != 64:
            raise ManifestError("Manifest 身份或 Hash 无效")
        manifest = RunManifest(
            run_id,
            "starting",
            baseline_hash,
            photo_hash,
            attempt_id,
            runtime_id=runtime_id,
            provider=provider,
            model=model,
            domain_pack_hash=domain_pack_hash,
        )
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

    def append_agent_event(self, manifest: RunManifest, event: AgentEvent) -> RunManifest:
        """消费统一 AgentEvent；Harness 原生事件不能直接成为状态真相源。"""
        if event.run_id != manifest.run_id or event.attempt_id != manifest.attempt_id:
            raise ManifestError("AgentEvent 不属于当前 Run/Attempt")
        event_id = hash_text(
            f"{event.run_id}:{event.attempt_id}:{event.sequence}:{event.kind.value}"
        )
        return self.append(
            manifest,
            event_id=event_id,
            sequence=event.sequence,
            kind=event.kind.value,
            payload=dict(event.payload),
        )

    def reconcile(self, manifest: RunManifest, *, baseline_hash: str) -> RunManifest:
        if manifest.status in {"starting", "running", "cancelling"}:
            manifest = replace(manifest, status="interrupted")
        if baseline_hash != manifest.baseline_hash:
            manifest = replace(manifest, status="stale", stale_reason="正式基线已变化")
        self._write_snapshot(manifest)
        return manifest

    def start_attempt(
        self,
        manifest: RunManifest,
        attempt_id: str,
        *,
        runtime_id: str | None = None,
    ) -> RunManifest:
        if manifest.status == "stale":
            raise ManifestError("stale 运行不能直接恢复")
        next_manifest = replace(
            manifest,
            attempt_id=attempt_id,
            status="starting",
            last_sequence=0,
            runtime_id=runtime_id or manifest.runtime_id,
        )
        self._write_snapshot(next_manifest)
        return next_manifest

    def _reduce(self, manifest: RunManifest, kind: str, sequence: int, payload: dict[str, Any]) -> RunManifest:
        status = manifest.status
        revision = manifest.last_candidate_revision
        if kind == "run_started":
            status = "running"
        elif kind == "candidate_created":
            revision = payload.get("revision") or revision
        elif kind == "run_finished":
            status = "completed"
        elif kind == "run_failed":
            status = "failed"
        return replace(
            manifest,
            status=status,
            last_sequence=sequence,
            last_candidate_revision=revision,
        )

    def _write_snapshot(self, manifest: RunManifest) -> None:
        target = self.path.with_suffix(".snapshot.json")
        fd, temporary = tempfile.mkstemp(prefix="manifest-", suffix=".json", dir=target.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(manifest.__dict__, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def hash_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


_RUN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


class RunManifestRepository:
    """按 Run ID 管理独立事实日志，不拥有 session_store 的正式编辑状态。"""

    RECOVERABLE = frozenset({"interrupted", "stale", "failed"})

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def store(self, run_id: str) -> RunManifestStore:
        if not _RUN_ID.fullmatch(run_id):
            raise ManifestError("Run ID 不安全")
        return RunManifestStore(self.root / f"{run_id}.jsonl")

    def create(self, run_id: str, **values: Any) -> RunManifest:
        store = self.store(run_id)
        if store.path.with_suffix(".snapshot.json").exists():
            raise ManifestError("Run Manifest 已存在")
        return store.create(run_id, **values)

    def load(self, run_id: str) -> RunManifest:
        return self.store(run_id).load()

    def list(self) -> tuple[RunManifest, ...]:
        manifests: list[RunManifest] = []
        for snapshot in sorted(self.root.glob("*.snapshot.json")):
            run_id = snapshot.name.removesuffix(".snapshot.json")
            try:
                manifests.append(self.load(run_id))
            except ManifestError:
                continue
        return tuple(manifests)

    def reconcile_startup(self) -> tuple[RunManifest, ...]:
        reconciled = []
        for manifest in self.list():
            reconciled.append(
                self.store(manifest.run_id).reconcile(
                    manifest,
                    baseline_hash=manifest.baseline_hash,
                )
            )
        return tuple(reconciled)

    def list_recoverable(self) -> tuple[RunManifest, ...]:
        return tuple(item for item in self.list() if item.status in self.RECOVERABLE)

    def start_attempt(
        self,
        run_id: str,
        *,
        attempt_id: str,
        baseline_hash: str,
        runtime_id: str | None = None,
    ) -> RunManifest:
        manifest = self.load(run_id)
        if baseline_hash != manifest.baseline_hash:
            stale = self.store(run_id).reconcile(
                manifest,
                baseline_hash=baseline_hash,
            )
            raise ManifestError(stale.stale_reason or "正式基线已变化")
        if manifest.status not in {"interrupted", "failed"}:
            raise ManifestError("只有中断或失败的 Run 可以新建 Attempt")
        return self.store(run_id).start_attempt(
            manifest,
            attempt_id,
            runtime_id=runtime_id,
        )
