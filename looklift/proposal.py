"""跨模块 Proposal 生命周期与幂等存储。"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Mapping


class ProposalError(ValueError):
    pass


@dataclass(frozen=True)
class Proposal:
    proposal_id: str
    target_type: str
    target_id: str
    base_hash: str
    patch: Mapping[str, Any]
    source_packet_ids: tuple[str, ...]
    expires_at: str
    status: str = "preview"
    applied_revision: str | None = None


class ProposalService:
    """ProposalStore/Service 唯一实现；具体目标通过 apply_target 回调接入。"""

    TARGETS = frozenset({"Memory", "ProjectContext", "Skill", "Template", "Reference"})
    STATUSES = frozenset({"preview", "confirmed", "rejected", "applied", "expired", "conflict"})

    def __init__(self, *, path: Path | None = None,
                 clock: Callable[[], datetime] | None = None) -> None:
        self._items: dict[str, Proposal] = {}
        self._path = Path(path) if path is not None else None
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._load()

    def preview(self, *, target_type: str, target_id: str, base_hash: str,
                patch: Mapping[str, Any], source_packet_ids: tuple[str, ...] = (),
                ttl: timedelta = timedelta(hours=24)) -> Proposal:
        if target_type not in self.TARGETS or not target_id or not base_hash:
            raise ProposalError("Proposal 目标或基线无效")
        if not isinstance(patch, Mapping):
            raise ProposalError("Proposal patch 必须是对象")
        if ttl <= timedelta(0):
            raise ProposalError("Proposal 有效期必须为正数")
        if not all(isinstance(item, str) and item for item in source_packet_ids):
            raise ProposalError("Proposal 来源 ID 不合法")
        try:
            json.dumps(patch, ensure_ascii=False, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ProposalError("Proposal patch 必须是合法 JSON") from exc
        proposal = Proposal(str(uuid.uuid4()), target_type, target_id, base_hash,
                            dict(patch), tuple(source_packet_ids),
                            (self._clock() + ttl).isoformat())
        self._items[proposal.proposal_id] = proposal
        self._persist()
        return proposal

    def list(self) -> tuple[Proposal, ...]:
        """按过期状态刷新后返回稳定列表。"""
        return tuple(self.get(proposal_id) for proposal_id in sorted(self._items))

    def get(self, proposal_id: str) -> Proposal:
        try:
            proposal = self._items[proposal_id]
        except KeyError as exc:
            raise ProposalError("Proposal 不存在") from exc
        if proposal.status in {"preview", "confirmed"} and self._expired(proposal):
            proposal = replace(proposal, status="expired")
            self._save(proposal)
        return proposal

    def confirm(self, proposal_id: str) -> Proposal:
        proposal = self.get(proposal_id)
        if proposal.status == "confirmed":
            return proposal
        if proposal.status != "preview":
            raise ProposalError("只有 preview Proposal 可以确认")
        return self._save(replace(proposal, status="confirmed"))

    def reject(self, proposal_id: str) -> Proposal:
        proposal = self.get(proposal_id)
        if proposal.status == "rejected":
            return proposal
        if proposal.status in {"applied", "expired"}:
            raise ProposalError("Proposal 当前不可拒绝")
        return self._save(replace(proposal, status="rejected"))

    def apply(self, proposal_id: str, *, current_hash: str,
              apply_target: Callable[[Proposal], str]) -> Proposal:
        proposal = self.get(proposal_id)
        if proposal.status in {"applied", "conflict"}:
            return proposal
        if proposal.status != "confirmed":
            raise ProposalError("Proposal 必须先确认")
        if proposal.base_hash != current_hash:
            return self._save(replace(proposal, status="conflict"))
        revision = apply_target(proposal)
        if not revision:
            raise ProposalError("目标适配器未返回 revision")
        return self._save(replace(proposal, status="applied", applied_revision=revision))

    def _save(self, proposal: Proposal) -> Proposal:
        self._items[proposal.proposal_id] = proposal
        self._persist()
        return proposal

    def _expired(self, proposal: Proposal) -> bool:
        return self._clock() >= datetime.fromisoformat(proposal.expires_at)

    def _load(self) -> None:
        if self._path is None or not self._path.is_file():
            return
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
            items = payload.get("proposals", [])
            for item in items:
                proposal = Proposal(
                    proposal_id=str(item["proposal_id"]),
                    target_type=str(item["target_type"]),
                    target_id=str(item["target_id"]),
                    base_hash=str(item["base_hash"]),
                    patch=dict(item["patch"]),
                    source_packet_ids=tuple(item.get("source_packet_ids", ())),
                    expires_at=str(item["expires_at"]),
                    status=str(item.get("status", "preview")),
                    applied_revision=item.get("applied_revision"),
                )
                if proposal.target_type not in self.TARGETS or proposal.status not in self.STATUSES:
                    raise ProposalError("Proposal 存储包含非法状态")
                self._items[proposal.proposal_id] = proposal
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ProposalError("Proposal 存储损坏") from exc

    def _persist(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "proposals": [
                {
                    "proposal_id": item.proposal_id,
                    "target_type": item.target_type,
                    "target_id": item.target_id,
                    "base_hash": item.base_hash,
                    "patch": dict(item.patch),
                    "source_packet_ids": list(item.source_packet_ids),
                    "expires_at": item.expires_at,
                    "status": item.status,
                    "applied_revision": item.applied_revision,
                }
                for item in sorted(self._items.values(), key=lambda value: value.proposal_id)
            ],
        }
        temporary = self._path.with_suffix(self._path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        temporary.replace(self._path)


def proposal_hash(proposal: Proposal) -> str:
    payload = {"target_type": proposal.target_type, "target_id": proposal.target_id,
               "base_hash": proposal.base_hash, "patch": proposal.patch,
               "source_packet_ids": proposal.source_packet_ids}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()
