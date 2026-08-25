"""消费 CandidateRuntime 证据的分层 Verifier、Critique 与用户复核门。"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import Any, Mapping


class FailureClass(StrEnum):
    CONTRACT = "contract"
    DOMAIN = "domain"
    CAPABILITY = "capability"
    RENDER = "render"


@dataclass(frozen=True)
class CritiquePolicy:
    max_highlight_clip_ratio: float = 0.05
    max_shadow_clip_ratio: float = 0.05


@dataclass(frozen=True)
class VerifierResult:
    status: str
    violations: tuple[str, ...] = ()
    metrics: Mapping[str, float] = field(default_factory=dict)
    evidence_hash: str = ""
    failure_class: FailureClass | None = None

    @property
    def hard_failed(self) -> bool:
        return self.status == "fail"


class CandidateVerifier:
    """不重新渲染，只消费不可变 Candidate Revision 的差异、预览和指标。"""

    def __init__(self, policy: CritiquePolicy | None = None) -> None:
        self._policy = policy or CritiquePolicy()

    def verify(
        self,
        candidate: Any,
        *,
        allowed_paths: set[str],
        skill_disabled: bool = False,
        capability_ok: bool = True,
    ) -> VerifierResult:
        metrics = _metrics(candidate)
        evidence_hash = _evidence_hash(candidate, metrics)
        invalid_paths = [
            change.path
            for change in getattr(candidate, "changes", ())
            if change.path not in allowed_paths
        ]
        if invalid_paths:
            return VerifierResult(
                "fail",
                tuple(f"非法参数路径：{path}" for path in invalid_paths),
                metrics,
                evidence_hash,
                FailureClass.CONTRACT,
            )
        if not getattr(candidate, "preview_jpeg", b""):
            return VerifierResult(
                "fail",
                ("候选缺少真实预览",),
                metrics,
                evidence_hash,
                FailureClass.RENDER,
            )
        if skill_disabled:
            return VerifierResult(
                "fail",
                ("Skill 禁用条件成立",),
                metrics,
                evidence_hash,
                FailureClass.DOMAIN,
            )
        if not capability_ok:
            return VerifierResult(
                "fail",
                ("运行时能力不足",),
                metrics,
                evidence_hash,
                FailureClass.CAPABILITY,
            )

        warnings: list[str] = []
        if metrics.get("highlight_clip_ratio", 0) > self._policy.max_highlight_clip_ratio:
            warnings.append("高光裁切比例超过 Critique 阈值")
        if metrics.get("shadow_clip_ratio", 0) > self._policy.max_shadow_clip_ratio:
            warnings.append("阴影裁切比例超过 Critique 阈值")
        return VerifierResult(
            "warn" if warnings else "pass",
            tuple(warnings),
            metrics,
            evidence_hash,
            FailureClass.RENDER if warnings else None,
        )


@dataclass(frozen=True)
class UserReview:
    candidate_id: str
    baseline_hash: str
    evidence_hash: str
    confirmed: bool = False


class UserReviewGate:
    """只记录用户确认意图；正式版本提交仍由 Session/Candidate 边界负责。"""

    def open(
        self,
        candidate: Any,
        result: VerifierResult,
        *,
        baseline_hash: str,
    ) -> UserReview:
        if result.hard_failed:
            raise ValueError("候选未通过硬门禁")
        return UserReview(
            candidate_id=str(candidate.candidate_id),
            baseline_hash=baseline_hash,
            evidence_hash=result.evidence_hash,
        )

    def confirm(self, review: UserReview, *, current_baseline_hash: str) -> UserReview:
        if review.baseline_hash != current_baseline_hash:
            raise ValueError("正式基线已变化")
        return replace(review, confirmed=True)


def critique(result: VerifierResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "messages": list(result.violations),
        "failure_class": result.failure_class.value if result.failure_class else None,
        "can_confirm": not result.hard_failed,
    }


def _metrics(candidate: Any) -> dict[str, float]:
    value = getattr(candidate, "metrics", None)
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        value = value.model_dump()
    return {key: float(item) for key, item in dict(value).items()}


def _evidence_hash(candidate: Any, metrics: Mapping[str, float]) -> str:
    preview = getattr(candidate, "preview_jpeg", b"")
    payload = json.dumps(
        {
            "candidate_id": str(getattr(candidate, "candidate_id", "")),
            "changes": [
                change.model_dump(mode="json")
                if hasattr(change, "model_dump")
                else str(change)
                for change in getattr(candidate, "changes", ())
            ],
            "metrics": metrics,
            "preview_hash": hashlib.sha256(preview).hexdigest(),
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()
