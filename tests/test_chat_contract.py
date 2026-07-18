"""v2.1 对话参数操作契约：白名单、原子应用与拒绝语义。"""
from __future__ import annotations

from copy import deepcopy

import pytest

from looklift.chat_contract import apply_chat_operations
from looklift.render.contract import ai_scalar_paths, param_bounds


def test_ai_scalar_paths_reuses_parameter_contract_and_excludes_curve():
    paths = ai_scalar_paths()

    assert isinstance(paths, tuple)
    assert "basic.exposure" in paths
    assert "hsl.blue.saturation" in paths
    assert "tone_curve" not in paths


def test_scalar_delta_set_and_clamp_are_applied_without_mutating_input(sample_analysis):
    original = deepcopy(sample_analysis)
    upper = param_bounds("basic.exposure")[1]

    result = apply_chat_operations(
        sample_analysis,
        [
            {
                "type": "scalar",
                "path": "basic.exposure",
                "mode": "delta",
                "value": 100,
                "reason": "提亮画面",
            },
            {
                "type": "scalar",
                "path": "effects.grain_amount",
                "mode": "set",
                "value": 12,
                "reason": "减少颗粒",
            },
        ],
    )

    assert sample_analysis == original
    assert result.analysis["basic"]["exposure"] == upper
    assert result.analysis["effects"]["grain_amount"] == 12
    assert [change["path"] for change in result.changes] == [
        "basic.exposure",
        "effects.grain_amount",
    ]
    assert result.changes[0] == {
        "type": "scalar",
        "path": "basic.exposure",
        "before": 0.35,
        "after": upper,
        "reason": "提亮画面",
    }
    assert result.rejected == ()


@pytest.mark.parametrize(
    ("operation", "reason_fragment"),
    [
        ({"type": "scalar", "path": "basic.unknown", "mode": "set", "value": 1}, "未知参数"),
        ({"type": "scalar", "path": "basic.exposure", "mode": "multiply", "value": 1}, "操作模式"),
        ({"type": "scalar", "path": "basic.exposure", "mode": "set", "value": True}, "有限数值"),
        ({"type": "scalar", "path": "basic.exposure", "mode": "set", "value": float("inf")}, "有限数值"),
        ({"type": "unknown"}, "未知操作"),
    ],
)
def test_invalid_scalar_operations_are_rejected_individually(
    sample_analysis, operation, reason_fragment
):
    original = deepcopy(sample_analysis)

    result = apply_chat_operations(sample_analysis, [operation])

    assert result.analysis == original
    assert result.changes == ()
    assert len(result.rejected) == 1
    assert result.rejected[0]["operation"] == operation
    assert reason_fragment in result.rejected[0]["reason"]


def test_empty_and_noop_operations_do_not_create_changes(sample_analysis):
    empty = apply_chat_operations(sample_analysis, [])
    noop = apply_chat_operations(
        sample_analysis,
        [{"type": "scalar", "path": "basic.exposure", "mode": "set", "value": 0.35}],
    )

    assert empty.changes == ()
    assert empty.rejected == ()
    assert noop.changes == ()
    assert len(noop.rejected) == 1
    assert "未产生变化" in noop.rejected[0]["reason"]


def test_valid_tone_curve_replaces_the_whole_curve_atomically(sample_analysis):
    original = deepcopy(sample_analysis)
    points = [
        {"input": 0, "output": 8},
        {"input": 96, "output": 88},
        {"input": 255, "output": 250},
    ]

    result = apply_chat_operations(
        sample_analysis,
        [{"type": "tone_curve", "points": points, "reason": "轻微压暗中间调"}],
    )

    assert sample_analysis == original
    assert result.analysis["tone_curve"] == points
    assert result.changes == ({
        "type": "tone_curve",
        "path": "tone_curve",
        "before": original["tone_curve"],
        "after": points,
        "reason": "轻微压暗中间调",
    },)
    assert result.rejected == ()


@pytest.mark.parametrize(
    "points",
    [
        [{"input": 0, "output": 0}],
        [{"input": 1, "output": 0}, {"input": 255, "output": 255}],
        [{"input": 0, "output": 0}, {"input": 254, "output": 255}],
        [{"input": 0, "output": 0}, {"input": 64, "output": 64}, {"input": 64, "output": 80}, {"input": 255, "output": 255}],
        [{"input": 0, "output": 0}, {"input": 128, "output": 300}, {"input": 255, "output": 255}],
        [{"input": 0, "output": 0}, {"input": True, "output": 80}, {"input": 255, "output": 255}],
        [{"input": 0, "output": 0}, {"input": "128", "output": 80}, {"input": 255, "output": 255}],
    ],
)
def test_invalid_tone_curve_is_rejected_as_a_whole(sample_analysis, points):
    original = deepcopy(sample_analysis)
    operation = {"type": "tone_curve", "points": points}

    result = apply_chat_operations(sample_analysis, [operation])

    assert result.analysis == original
    assert result.changes == ()
    assert len(result.rejected) == 1
    assert result.rejected[0]["operation"] == operation
    assert "曲线" in result.rejected[0]["reason"]


def test_invalid_curve_does_not_rollback_other_valid_operations(sample_analysis):
    bad_curve = [{"input": 0, "output": 0}, {"input": 0, "output": 12}]

    result = apply_chat_operations(
        sample_analysis,
        [
            {"type": "scalar", "path": "basic.contrast", "mode": "delta", "value": 5},
            {"type": "tone_curve", "points": bad_curve},
        ],
    )

    assert result.analysis["basic"]["contrast"] == 23
    assert result.analysis["tone_curve"] == sample_analysis["tone_curve"]
    assert len(result.changes) == 1
    assert len(result.rejected) == 1
