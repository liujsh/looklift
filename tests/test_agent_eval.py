"""v2.6-D 默认离线 Case 与消融运行器测试。"""

from __future__ import annotations

from looklift.agent_eval import (
    EVAL_CASES,
    AblationConfig,
    run_all_eval_cases,
    run_eval_case,
)


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

