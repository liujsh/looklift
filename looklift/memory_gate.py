"""Agent 自动记忆写入前的确定性策略门。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .context_memory import ContextEntry


@dataclass(frozen=True)
class MemoryCandidate:
    entry_id: str
    entry_type: str
    content: str
    source: str
    scope: str = "global"
    project_id: str | None = None
    run_id: str | None = None
    expires_at: str | None = None
    name: str = ""
    description: str = ""
    confidence: float = 1.0
    evidence: str = ""
    source_event_id: str | None = None
    explicit_remember: bool = False


@dataclass(frozen=True)
class GateDecision:
    action: str  # write / merge / downgrade / skip
    candidate: MemoryCandidate | None
    reason: str
    duplicate_id: str | None = None


class MemoryGate:
    """无模型调用的自动写入策略；模型只提供候选，Gate 决定是否落盘。"""

    _SENSITIVE_MARKERS = ("api_key", "access_token", "bearer ", "sk-")
    _TRANSIENT_PREFIXES = ("这张", "这一张", "本次", "刚才", "临时")

    def evaluate(
        self,
        candidate: MemoryCandidate,
        existing: Iterable[ContextEntry] = (),
    ) -> GateDecision:
        if not candidate.content.strip():
            return GateDecision("skip", None, "empty-content")
        lowered = candidate.content.lower()
        if any(marker in lowered for marker in self._SENSITIVE_MARKERS):
            return GateDecision("skip", None, "sensitive-content")
        if candidate.scope not in {"global", "project", "run"}:
            return GateDecision("skip", None, "invalid-scope")
        if candidate.scope == "project" and not candidate.project_id:
            return GateDecision("skip", None, "project-id-required")
        if candidate.scope == "run" and (not candidate.run_id or not candidate.expires_at):
            return GateDecision("skip", None, "run-lifecycle-required")
        if not 0 <= candidate.confidence <= 1:
            return GateDecision("skip", None, "invalid-confidence")

        normalized = self._normalize(candidate.content)
        for item in existing:
            if self._normalize(item.content) == normalized and item.entry_type == candidate.entry_type:
                return GateDecision("merge", candidate, "duplicate-content", item.entry_id)

        # 单次操作默认不得污染 global；明确记忆命令可保留用户指定作用域。
        if (
            candidate.scope == "global"
            and not candidate.explicit_remember
            and candidate.content.lstrip().startswith(self._TRANSIENT_PREFIXES)
        ):
            downgraded = MemoryCandidate(**{**candidate.__dict__, "scope": "run"})
            if not downgraded.run_id or not downgraded.expires_at:
                return GateDecision("skip", None, "transient-needs-run-lifecycle")
            return GateDecision("downgrade", downgraded, "transient-downgraded-to-run")

        if candidate.entry_type == "rule" and candidate.scope == "global" and candidate.confidence < 0.9:
            return GateDecision("skip", None, "global-rule-confidence-too-low")
        return GateDecision("write", candidate, "gate-accepted")

    @staticmethod
    def _normalize(value: str) -> str:
        return " ".join(value.casefold().split())
