"""跨模块 Proposal 生命周期与幂等存储。"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
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

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._items: dict[str, Proposal] = {}
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def preview(self, *, target_type: str, target_id: str, base_hash: str,
                patch: Mapping[str, Any], source_packet_ids: tuple[str, ...] = (),
                ttl: timedelta = timedelta(hours=24)) -> Proposal:
        if target_type not in self.TARGETS or not target_id or not base_hash:
            raise ProposalError("Proposal 目标或基线无效")
        if not isinstance(patch, Mapping):
            raise ProposalError("Proposal patch 必须是对象")
        proposal = Proposal(str(uuid.uuid4()), target_type, target_id, base_hash,
                            dict(patch), tuple(source_packet_ids),
                            (self._clock() + ttl).isoformat())
        self._items[proposal.proposal_id] = proposal
        return proposal

    def get(self, proposal_id: str) -> Proposal:
        try:
            proposal = self._items[proposal_id]
        except KeyError as exc:
            raise ProposalError("Proposal 不存在") from exc
        if proposal.status in {"preview", "confirmed"} and self._expired(proposal):
            proposal = replace(proposal, status="expired")
            self._items[proposal_id] = proposal
        return proposal

    def confirm(self, proposal_id: str) -> Proposal:
        proposal = self.get(proposal_id)
        if proposal.status != "preview":
            raise ProposalError("只有 preview Proposal 可以确认")
        return self._save(replace(proposal, status="confirmed"))

    def reject(self, proposal_id: str) -> Proposal:
        proposal = self.get(proposal_id)
        if proposal.status in {"applied", "expired"}:
            raise ProposalError("Proposal 当前不可拒绝")
        return self._save(replace(proposal, status="rejected"))

    def apply(self, proposal_id: str, *, current_hash: str,
              apply_target: Callable[[Proposal], str]) -> Proposal:
        proposal = self.get(proposal_id)
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
        return proposal

    def _expired(self, proposal: Proposal) -> bool:
        return self._clock() >= datetime.fromisoformat(proposal.expires_at)


def proposal_hash(proposal: Proposal) -> str:
    payload = {"target_type": proposal.target_type, "target_id": proposal.target_id,
               "base_hash": proposal.base_hash, "patch": proposal.patch,
               "source_packet_ids": proposal.source_packet_ids}
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()
