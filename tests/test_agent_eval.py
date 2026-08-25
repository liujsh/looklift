"""v2.6-D 默认离线 Case 与消融运行器测试。"""

from __future__ import annotations

from looklift.agent_eval import (
    EVAL_DATASET_VERSION,
    EVAL_CASES,
    AblationConfig,
    build_eval_report,
    run_ablation_matrix,
    run_all_eval_cases,
    run_eval_case,
)
import json
import pytest


def test_eval_dataset_contains_twelve_effect_and_eight_engineering_cases() -> None:
    assert len(EVAL_CASES) == 20
    assert sum(case.kind == "effect" for case in EVAL_CASES) == 12
    assert sum(case.kind in {"engineering", "security"} for case in EVAL_CASES) == 8
    assert len({case.case_id for case in EVAL_CASES}) == 20


def test_all_default_cases_are_deterministic_and_have_no_formal_side_effect() -> None:
    first = run_all_eval_cases()
    second = run_all_eval_cases()
    assert first == second
    assert all(result.passed for result in first)
    assert all(not result.formal_side_effects for result in first)
    assert all(not result.leaked_sensitive_data for result in first)


def test_ablation_dimensions_are_accepted_without_changing_fake_safety_boundary() -> None:
    case = next(case for case in EVAL_CASES if case.case_id == "effect-01")
    result = run_eval_case(
        case,
        config=AblationConfig(
            skill_enabled=False,
            template_mode="matched",
            feedback_mode="render_only",
        ),
    )
    assert result.passed is True
    assert result.formal_side_effects is False


def test_eval_result_contains_auditable_trace_invariants_and_pending_manual_gates():
    result = run_eval_case(EVAL_CASES[0])
    payload = result.to_dict()

    assert result.dataset_version == EVAL_DATASET_VERSION
    assert result.trace == ("run_started", "text_delta", "tool_started", "candidate_created", "run_finished")
    assert result.failure_class is None
    assert result.formal_version_unchanged is True
    assert result.candidate_versions_monotonic is True
    assert result.cancelled is False
    assert result.late_result_isolated is True
    assert result.real_model_status == "pending_manual"
    assert result.human_pairwise_status == "pending_manual"
    json.dumps(payload, ensure_ascii=False)


def test_security_failures_are_classified_and_never_leak_sensitive_data():
    result = next(run_eval_case(case) for case in EVAL_CASES if case.case_id == "engineering-01")

    assert result.failure_class == "policy"
    assert result.formal_version_unchanged is True
    assert result.leaked_sensitive_data is False
    assert result.sensitive_data_findings == ()


def test_insufficient_capability_is_a_domain_failure_and_invalid_ablation_is_rejected():
    result = run_eval_case(next(case for case in EVAL_CASES if case.expected_outcome == "insufficient_capability"))

    assert result.failure_class == "capability"
    with pytest.raises(ValueError, match="消融模式"):
        AblationConfig(template_mode="invalid")  # type: ignore[arg-type]


def test_ablation_matrix_covers_three_dimensions_and_preserves_safety_boundary():
    matrix = run_ablation_matrix(case_ids=("effect-01",))

    assert len(matrix) == 6
    assert {(item.config.skill_enabled, item.config.template_mode, item.config.feedback_mode) for item in matrix} == {
        (False, "none", "render_only"), (False, "matched", "render_only"),
        (False, "mismatched", "render_only"), (True, "none", "image_and_metrics"),
        (True, "matched", "image_and_metrics"), (True, "mismatched", "image_and_metrics"),
    }
    assert all(item.result.formal_version_unchanged for item in matrix)


def test_report_has_separate_automation_real_model_and_human_stages():
    report = build_eval_report(case_ids=("effect-01", "engineering-01"))

    assert report["dataset_version"] == EVAL_DATASET_VERSION
    assert report["summary"]["total"] == 2
    assert report["stages"] == {
        "offline_contract": "passed",
        "fake_harness": "passed",
        "real_model_ablation": "pending_manual",
        "human_pairwise": "pending_manual",
    }
    json.dumps(report, ensure_ascii=False)

