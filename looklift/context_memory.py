"""Global Rules、Memory、Project Context 的可审查存储与快照。"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from pathlib import Path

from .proposal import Proposal, ProposalService


@dataclass(frozen=True)
class ContextEntry:
    entry_id: str
    entry_type: str
    content: str
    source: str
    version: int = 1
    confirmed: bool = False
    enabled: bool = True

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(self.content.encode("utf-8")).hexdigest()


class ContextMemoryStore:
    """Markdown-backed 的最小实现；正式写入只能通过 ProposalService。"""

    TYPES = frozenset({"rule", "fact", "preference", "project", "reference", "feedback"})

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.proposals = ProposalService()
        self._entries: dict[str, ContextEntry] = {}

    def put(self, entry: ContextEntry) -> ContextEntry:
        if entry.entry_type not in self.TYPES or not entry.entry_id or not entry.content.strip():
            raise ValueError("Context 条目不合法")
        self._entries[entry.entry_id] = entry
        path = self.root / f"{entry.entry_id}.md"
        path.write_text(
            f"---\nid: {entry.entry_id}\ntype: {entry.entry_type}\nversion: {entry.version}\n"
            f"confirmed: {str(entry.confirmed).lower()}\nsource: {entry.source}\n---\n\n{entry.content}\n",
            encoding="utf-8",
        )
        return entry

    def get(self, entry_id: str) -> ContextEntry:
        return self._entries[entry_id]

    def snapshot(self) -> tuple[ContextEntry, ...]:
        return tuple(replace(item) for item in self._entries.values() if item.enabled)

    def proposal(self, *, target_id: str, content: str, base_hash: str,
                 source_packet_ids: tuple[str, ...] = ()) -> Proposal:
        if target_id not in self._entries:
            raise KeyError(target_id)
        return self.proposals.preview(target_type="Memory", target_id=target_id, base_hash=base_hash,
                                      patch={"content": content}, source_packet_ids=source_packet_ids)

    def apply_proposal(self, proposal_id: str) -> Proposal:
        proposal = self.proposals.get(proposal_id)
        target = self.get(proposal.target_id)
        return self.proposals.apply(proposal_id, current_hash=target.content_hash,
                                    apply_target=self._apply)

    def _apply(self, proposal: Proposal) -> str:
        target = self.get(proposal.target_id)
        updated = replace(target, content=str(proposal.patch["content"]), version=target.version + 1, confirmed=True)
        self.put(updated)
        return updated.content_hash
