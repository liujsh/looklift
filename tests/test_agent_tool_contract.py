"""候选工具、相对 Template 与结构化终态的契约测试。"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from looklift.agent_tool_contract import (
    AgentTemplate,
    CurvePoint,
    FinishCandidateInput,
    RenderCandidateInput,
    ScalarOperation,
    ToneCurveOperation,
)
from looklift.render.contract import ai_scalar_paths


def test_scalar_path_schema_is_generated_from_render_contract() -> None:
    schema = ScalarOperation.model_json_schema()

    assert schema["properties"]["path"]["enum"] == list(ai_scalar_paths())


def test_scalar_operation_rejects_unknown_path_and_out_of_range_set() -> None:
    with pytest.raises(ValidationError, match="未知参数路径"):
        ScalarOperation(
            type="scalar",
            path="local.mask",
            mode="set",
            value=1,
            reason="越权",
        )

    with pytest.raises(ValidationError, match="超出参数范围"):
        ScalarOperation(
            type="scalar",
            path="basic.exposure",
            mode="set",
            value=99,
            reason="越界",
        )


def test_delta_range_is_deferred_until_current_baseline_is_known() -> None:
    operation = ScalarOperation(
        type="scalar",
        path="basic.exposure",
        mode="delta",
        value=1.5,
        reason="相对调整",
    )

    assert operation.value == 1.5


def test_tone_curve_contract_rejects_non_monotonic_or_missing_endpoints() -> None:
    with pytest.raises(ValidationError, match="严格递增"):
        ToneCurveOperation(
            type="tone_curve",
            points=[
                CurvePoint(input=0, output=0),
                CurvePoint(input=0, output=20),
                CurvePoint(input=255, output=255),
            ],
            reason="错误曲线",
        )

    with pytest.raises(ValidationError, match="完整起止端点"):
        ToneCurveOperation(
            type="tone_curve",
            points=[
                CurvePoint(input=10, output=10),
                CurvePoint(input=255, output=255),
            ],
            reason="缺端点",
        )


def test_render_input_accepts_template_only_first_candidate() -> None:
    value = RenderCandidateInput(
        operations=[],
        intent="先采用用户选择的模板",
        template_strength=0.5,
    )

    assert value.template_strength == 0.5
    assert value.operations == ()


def test_agent_template_only_accepts_versioned_scalar_relative_patch() -> None:
    template = AgentTemplate(
        template_id="portrait-soft",
        version=1,
        name="柔和人像起点",
        scene_tags=["portrait"],
        intent_tags=["soft"],
        expected_effect="降低生硬反差",
        contraindications=["严重欠曝"],
        risks=["背景可能变平"],
        compatible_skills=["portrait-natural"],
        operations=[
            ScalarOperation(
                type="scalar",
                path="basic.contrast",
                mode="delta",
                value=-10,
                reason="降低反差",
            )
        ],
    )

    assert template.operations[0].path == "basic.contrast"
    assert template.version == 1

    with pytest.raises(ValidationError):
        AgentTemplate(
            template_id="bad-template",
            version=1,
            name="错误模板",
            scene_tags=["portrait"],
            intent_tags=["soft"],
            expected_effect="错误",
            contraindications=[],
            risks=[],
            compatible_skills=[],
            operations=[
                ToneCurveOperation(
                    type="tone_curve",
                    points=[
                        CurvePoint(input=0, output=0),
                        CurvePoint(input=255, output=255),
                    ],
                    reason="模板不允许曲线",
                )
            ],
        )


def test_finish_candidate_enforces_outcome_specific_fields() -> None:
    ready = FinishCandidateInput(
        outcome="candidate_ready",
        candidate_id="candidate-1",
        summary="主体层次更自然",
        review_items=["复核面部高光"],
        uncertainties=[],
        limitations=[],
    )
    no_change = FinishCandidateInput(
        outcome="no_change_needed",
        summary="当前效果已经满足目标",
        review_items=[],
        uncertainties=[],
        limitations=[],
    )
    insufficient = FinishCandidateInput(
        outcome="insufficient_capability",
        summary="需要局部蒙版",
        review_items=[],
        uncertainties=["主体边缘无法可靠分割"],
        limitations=["当前只支持全局白盒参数"],
    )

    assert ready.candidate_id == "candidate-1"
    assert no_change.candidate_id is None
    assert insufficient.limitations

    with pytest.raises(ValidationError, match="candidate_id"):
        FinishCandidateInput(
            outcome="candidate_ready",
            summary="缺少候选",
            review_items=[],
            uncertainties=[],
            limitations=[],
        )
    with pytest.raises(ValidationError, match="limitations"):
        FinishCandidateInput(
            outcome="insufficient_capability",
            summary="能力不足",
            review_items=[],
            uncertainties=[],
            limitations=[],
        )
