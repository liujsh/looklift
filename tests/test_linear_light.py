import copy

import numpy as np
import pytest

from looklift.render import color_space as cs
from looklift.render import pipeline
from looklift.render.base import Domain
from looklift.render.operators.basic import Exposure, WhiteBalance
from looklift.render.operators.color import ColorGrading


def _zero_analysis(sample_analysis):
    """清零分析参数，隔离单个线性光行为。"""
    analysis = copy.deepcopy(sample_analysis)
    analysis["basic"] = {key: 0 for key in analysis["basic"]}
    analysis["tone_curve"] = []
    analysis["hsl"] = []
    for zone in ("shadows", "midtones", "highlights", "global_"):
        analysis["color_grading"][zone] = {
            "hue": 0,
            "saturation": 0,
            "luminance": 0,
        }
    analysis["effects"] = {"vignette_amount": 0, "grain_amount": 0}
    return analysis


@pytest.mark.parametrize(("ev", "expected"), [(1.0, 2.0), (2.0, 4.0)])
def test_exposure_ev_scales_linear_light(sample_analysis, ev, expected):
    """曝光每增加一档，线性光能量精确翻倍。"""
    analysis = _zero_analysis(sample_analysis)
    analysis["basic"]["exposure"] = ev
    src = np.full((8, 8, 3), 0.2, dtype=np.float32)

    out = pipeline.render_arr(src.copy(), analysis)

    ratio = cs.srgb_to_linear(out)[0, 0, 0] / cs.srgb_to_linear(src)[0, 0, 0]
    assert ratio == pytest.approx(expected, rel=0.01)


def test_white_balance_uses_linear_channel_gains(sample_analysis):
    """白平衡通道增益作用于线性光，而非 sRGB 编码值。"""
    analysis = _zero_analysis(sample_analysis)
    analysis["basic"]["temperature_shift"] = 50
    analysis["basic"]["tint_shift"] = 40
    src = np.full((4, 4, 3), 0.3, dtype=np.float32)

    out = pipeline.render_arr(src.copy(), analysis)

    gains = cs.srgb_to_linear(out)[0, 0] / cs.srgb_to_linear(src)[0, 0]
    np.testing.assert_allclose(gains, [1.1, 0.94, 0.9], rtol=0.01)


def test_linear_segment_preserves_values_above_one_until_oetf(
    sample_analysis, monkeypatch
):
    """线性段中间值可超过 1，只在进入显示阶段后按契约收拢。"""
    analysis = _zero_analysis(sample_analysis)
    analysis["basic"]["exposure"] = 2.0
    src = np.full((4, 4, 3), 0.9, dtype=np.float32)
    observed = {}
    real_linear_to_srgb = cs.linear_to_srgb

    def observe_linear_input(arr):
        observed["before_oetf"] = arr.copy()
        return real_linear_to_srgb(arr)

    monkeypatch.setattr(pipeline.cs, "linear_to_srgb", observe_linear_input)
    out = pipeline.render_arr(src.copy(), analysis)

    assert observed["before_oetf"].max() > 1.0
    assert out.max() <= 1.0
    assert out.mean() > 0.95


def test_operator_domains_move_only_exposure_and_white_balance_to_linear():
    assert Exposure.domain is Domain.LINEAR
    assert WhiteBalance.domain is Domain.LINEAR
    assert ColorGrading.domain is Domain.DISPLAY


def test_color_grading_blending_and_balance_remain_contract_only(sample_analysis):
    analysis = _zero_analysis(sample_analysis)
    analysis["color_grading"]["global_"] = {
        "hue": 210,
        "saturation": 50,
        "luminance": 20,
    }
    src = np.full((4, 4, 3), 0.4, dtype=np.float32)
    baseline = pipeline.render_arr(src.copy(), analysis)
    analysis["color_grading"]["blending"] = 0
    analysis["color_grading"]["balance"] = 100

    changed = pipeline.render_arr(src.copy(), analysis)

    np.testing.assert_array_equal(changed, baseline)
