"""候选分层验证与 Critique 结果规范化。"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class VerifierResult:
    status: str
    violations: tuple[str, ...] = ()
    metrics: Mapping[str, float] = field(default_factory=dict)
    evidence_hash: str = ""
    failure_class: str | None = None

    @property
    def hard_failed(self) -> bool:
        return self.status == "fail"


class CandidateVerifier:
    """只消费 CandidateRuntime 已产生的参数/预览/指标证据。"""

    def verify(self, candidate: Any, *, allowed_paths: set[str], skill_disabled: bool = False,
               capability_ok: bool = True) -> VerifierResult:
        violations: list[str] = []
        operations = getattr(candidate, "operations", ())
        for operation in operations:
            path = getattr(operation, "path", "")
            if path not in allowed_paths:
                violations.append(f"非法参数路径：{path}")
        if skill_disabled:
            violations.append("Skill 禁用条件成立")
        if not capability_ok:
            violations.append("运行时能力不足")
        if violations:
            return VerifierResult("fail", tuple(violations), failure_class="contract_or_domain")
        metrics = getattr(candidate, "metrics", {}) or {}
        return VerifierResult("pass", metrics=metrics)


def critique(result: VerifierResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "messages": list(result.violations),
        "failure_class": result.failure_class,
        "can_confirm": not result.hard_failed,
    }
