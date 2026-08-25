from __future__ import annotations

from types import SimpleNamespace

import pytest

from looklift.agent_tool_contract import CandidateMetrics, ParameterChange
from looklift.verifier import (
    CandidateVerifier,
    CritiquePolicy,
    FailureClass,
    UserReviewGate,
    critique,
)
from looklift.candidate_runtime_types import CandidateRevision


def _candidate(*, path="basic.exposure", highlight=0.01, preview=b"jpeg"):
    return SimpleNamespace(
        candidate_id="candidate-1",
        changes=(ParameterChange(type="scalar", path=path, before=0, after=0.2, reason="提亮"),),
        metrics=CandidateMetrics(mean_luminance=0.5, shadow_clip_ratio=0.01, highlight_clip_ratio=highlight),
        preview_jpeg=preview,
    )


def test_verifier_uses_revision_evidence_and_hard_contract_gate():
    result = CandidateVerifier().verify(_candidate(path="unknown"), allowed_paths={"basic.exposure"})
    assert result.status == "fail"
    assert result.failure_class is FailureClass.CONTRACT
    assert len(result.evidence_hash) == 64


def test_render_threshold_is_warning_and_critique_remains_reviewable():
    result = CandidateVerifier(CritiquePolicy(max_highlight_clip_ratio=0.02)).verify(
        _candidate(highlight=0.05),
        allowed_paths={"basic.exposure"},
    )
    assert result.status == "warn"
    assert result.failure_class is FailureClass.RENDER
    assert critique(result)["can_confirm"] is True


def test_user_review_gate_never_commits_and_rechecks_baseline():
    gate = UserReviewGate()
    passed = CandidateVerifier().verify(_candidate(), allowed_paths={"basic.exposure"})
    review = gate.open(_candidate(), passed, baseline_hash="a" * 64)
    assert review.candidate_id == "candidate-1"
    assert review.confirmed is False
    with pytest.raises(ValueError, match="基线"):
        gate.confirm(review, current_baseline_hash="b" * 64)


def test_hard_failure_cannot_open_review_gate():
    failed = CandidateVerifier().verify(
        _candidate(),
        allowed_paths={"basic.exposure"},
        capability_ok=False,
    )
    with pytest.raises(ValueError, match="硬门禁"):
        UserReviewGate().open(_candidate(), failed, baseline_hash="a" * 64)


def test_verifier_consumes_real_candidate_revision_without_rerendering():
    revision = CandidateRevision(
        candidate_id="candidate-real",
        parent_candidate_id=None,
        _analysis_json='{"basic":{"exposure":0.2}}',
        preview_jpeg=b"rendered-preview",
        metrics=CandidateMetrics(
            mean_luminance=0.5,
            shadow_clip_ratio=0.01,
            highlight_clip_ratio=0.01,
        ),
        _changes_json='[{"type":"scalar","path":"basic.exposure","before":0,"after":0.2,"reason":"提亮"}]',
    )
    result = CandidateVerifier().verify(
        revision,
        allowed_paths={"basic.exposure"},
    )
    assert result.status == "pass"
    assert len(result.evidence_hash) == 64
