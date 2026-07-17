import copy

import numpy as np

from looklift.render import _legacy, pipeline


def _gray(v=0.5, size=(16, 16)):
    return np.full((*size, 3), v, dtype=np.float32)


def _zero(sample_analysis):
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


def test_display_pipeline_numerically_identical_to_legacy(sample_analysis):
    """纯搬家验证：新 display 串联与旧色彩管线的误差不超过 1/255。"""
    rng = np.random.default_rng(0)
    arr = rng.random((16, 16, 3)).astype(np.float32)
    legacy = _legacy._apply_color_ops(arr.copy(), sample_analysis)
    new = pipeline.apply_color_ops_numpy(arr.copy(), sample_analysis)
    assert np.max(np.abs(new - legacy)) <= 1.0 / 255


def test_display_pipeline_preserves_legacy_magenta_center(sample_analysis):
    analysis = _zero(sample_analysis)
    analysis["hsl"] = [
        {"color": "magenta", "hue": 0, "saturation": 100, "luminance": 0}
    ]
    hsv = np.asarray([[[320.0, 0.5, 0.8]]], dtype=np.float32)
    arr = _legacy._hsv_to_rgb(hsv)
    expected = _legacy._apply_color_ops(arr.copy(), analysis)
    actual = pipeline.apply_color_ops_numpy(arr.copy(), analysis)
    np.testing.assert_allclose(actual, expected, atol=1e-7)


def test_hsl_and_negative_saturation_preserve_legacy_overrange_hsv(sample_analysis):
    analysis = _zero(sample_analysis)
    analysis["hsl"] = [
        {"color": "red", "hue": 0, "saturation": 100, "luminance": 0}
    ]
    analysis["basic"]["saturation"] = -50
    arr = np.asarray(
        [
            [[0.0, 0.0, 0.0], [1.0, 1.0, 1.0]],
            [[1.0, 0.2, 0.2], [0.0, 1.0, 1.0]],
        ],
        dtype=np.float32,
    )
    expected = _legacy._apply_color_ops(arr.copy(), analysis)
    actual = pipeline.apply_color_ops_numpy(arr.copy(), analysis)
    assert np.max(np.abs(actual - expected)) <= 1.0 / 255


def test_hsl_only_restores_legacy_final_saturation_clip(sample_analysis):
    analysis = _zero(sample_analysis)
    analysis["hsl"] = [
        {"color": "orange", "hue": 0, "saturation": 100, "luminance": 0}
    ]
    hsv = np.asarray([[[30.0, 0.8, 1.0]]], dtype=np.float32)
    arr = _legacy._hsv_to_rgb(hsv)
    expected = _legacy._apply_color_ops(arr.copy(), analysis)
    actual = pipeline.apply_color_ops_numpy(arr.copy(), analysis)
    assert np.max(np.abs(actual - expected)) <= 1.0 / 255


def test_exposure_operator_direction_and_zero(sample_analysis):
    from looklift.render.operators.basic import Exposure

    op = Exposure()
    analysis = _zero(sample_analysis)
    assert op.resolve(analysis) is None
    analysis["basic"]["exposure"] = 1.0
    assert op.apply_numpy(_gray(0.25), op.resolve(analysis)).mean() > 0.25
    analysis["basic"]["exposure"] = -1.0
    assert op.apply_numpy(_gray(0.25), op.resolve(analysis)).mean() < 0.25


def test_white_balance_operator_direction_and_zero(sample_analysis):
    from looklift.render.operators.basic import WhiteBalance

    op = WhiteBalance()
    analysis = _zero(sample_analysis)
    assert op.resolve(analysis) is None
    analysis["basic"]["temperature_shift"] = 100
    warm = op.apply_numpy(_gray(), op.resolve(analysis))[0, 0]
    assert warm[0] > warm[2]
    analysis["basic"]["temperature_shift"] = -100
    cool = op.apply_numpy(_gray(), op.resolve(analysis))[0, 0]
    assert cool[0] < cool[2]
    analysis["basic"]["temperature_shift"] = 0
    analysis["basic"]["tint_shift"] = 100
    magenta = op.apply_numpy(_gray(), op.resolve(analysis))[0, 0]
    assert magenta[1] < magenta[0]


def test_contrast_operator_direction_and_zero(sample_analysis):
    from looklift.render.operators.basic import Contrast

    op = Contrast()
    analysis = _zero(sample_analysis)
    assert op.resolve(analysis) is None
    arr = np.asarray([[[0.3, 0.3, 0.3], [0.7, 0.7, 0.7]]], np.float32)
    analysis["basic"]["contrast"] = 50
    out = op.apply_numpy(arr, op.resolve(analysis))
    assert np.ptp(out[..., 0]) > 0.4
    analysis["basic"]["contrast"] = -50
    out = op.apply_numpy(arr, op.resolve(analysis))
    assert np.ptp(out[..., 0]) < 0.4


def test_highlights_shadows_operator_directions_and_zero(sample_analysis):
    from looklift.render.operators.basic import HighlightsShadows

    op = HighlightsShadows()
    analysis = _zero(sample_analysis)
    assert op.resolve(analysis) is None
    analysis["basic"]["highlights"] = 100
    assert op.apply_numpy(_gray(0.8), op.resolve(analysis)).mean() > 0.8
    analysis["basic"]["highlights"] = -100
    assert op.apply_numpy(_gray(0.8), op.resolve(analysis)).mean() < 0.8
    analysis["basic"]["highlights"] = 0
    analysis["basic"]["shadows"] = 100
    assert op.apply_numpy(_gray(0.2), op.resolve(analysis)).mean() > 0.2
    analysis["basic"]["shadows"] = -100
    assert op.apply_numpy(_gray(0.2), op.resolve(analysis)).mean() < 0.2


def test_whites_blacks_operator_directions_and_zero(sample_analysis):
    from looklift.render.operators.basic import WhitesBlacks

    op = WhitesBlacks()
    analysis = _zero(sample_analysis)
    assert op.resolve(analysis) is None
    analysis["basic"]["whites"] = 100
    assert op.apply_numpy(_gray(0.8), op.resolve(analysis)).mean() > 0.8
    analysis["basic"]["whites"] = -100
    assert op.apply_numpy(_gray(0.8), op.resolve(analysis)).mean() < 0.8
    analysis["basic"]["whites"] = 0
    analysis["basic"]["blacks"] = 100
    assert op.apply_numpy(_gray(0.1), op.resolve(analysis)).mean() > 0.1
    analysis["basic"]["blacks"] = -100
    assert op.apply_numpy(_gray(0.1), op.resolve(analysis)).mean() < 0.1


def test_tone_curve_resolve_bakes_fixed_float32_lut(sample_analysis):
    from looklift.render.operators.tone import ToneCurve

    op = ToneCurve()
    analysis = _zero(sample_analysis)
    assert op.resolve(analysis) is None
    analysis["tone_curve"] = [
        {"input": 0, "output": 10},
        {"input": 128, "output": 150},
        {"input": 255, "output": 245},
    ]
    (lut,) = op.resolve(analysis)
    grid = np.linspace(0.0, 1.0, 1024, dtype=np.float32)
    expected = np.interp(
        grid,
        np.asarray([0, 128, 255], np.float32) / 255.0,
        np.asarray([10, 150, 245], np.float32) / 255.0,
    ).astype(np.float32)
    assert lut.shape == (1024,) and lut.dtype == np.float32
    assert lut.flags.c_contiguous
    np.testing.assert_array_equal(lut, expected)
    rgb = (0.2, 0.5, 0.8)
    px = op.apply_px(rgb[0], rgb[1], rgb[2], lut)
    ref = op.apply_numpy(np.asarray(rgb, np.float32), (lut,))
    assert np.allclose(px, ref, atol=1e-7)


def test_tone_curve_operator_directions(sample_analysis):
    from looklift.render.operators.tone import ToneCurve

    op = ToneCurve()
    analysis = _zero(sample_analysis)
    analysis["tone_curve"] = [{"input": 0, "output": 20}, {"input": 255, "output": 255}]
    assert op.apply_numpy(_gray(0.2), op.resolve(analysis)).mean() > 0.2
    analysis["tone_curve"] = [{"input": 0, "output": 0}, {"input": 255, "output": 235}]
    assert op.apply_numpy(_gray(0.8), op.resolve(analysis)).mean() < 0.8


def test_tone_curve_extends_partial_curve_with_unit_slope(sample_analysis):
    from looklift.render.operators.tone import ToneCurve

    analysis = _zero(sample_analysis)
    analysis["tone_curve"] = [
        {"input": 10, "output": 20},
        {"input": 245, "output": 235},
    ]
    (lut,) = ToneCurve().resolve(analysis)
    assert lut[0] == np.float32(10 / 255)
    assert lut[-1] == np.float32(245 / 255)


def test_hsl_centers_keys_derive_from_analyzer_color_keys():
    from looklift.analyzer import _COLOR_KEYS
    from looklift.render.operators.color import _HSL_CENTERS

    assert tuple(_HSL_CENTERS) == tuple(_COLOR_KEYS)


def test_hsl_operator_directions_and_zero(sample_analysis):
    from looklift.render.operators.color import Hsl

    op = Hsl()
    analysis = _zero(sample_analysis)
    assert op.resolve(analysis) is None
    red = np.asarray([[[1.0, 0.2, 0.2]]], np.float32)
    analysis["hsl"] = [{"color": "red", "hue": 0, "saturation": 100, "luminance": 0}]
    saturated = op.apply_numpy(red, op.resolve(analysis))
    analysis["hsl"][0]["saturation"] = -100
    desaturated = op.apply_numpy(red, op.resolve(analysis))
    assert np.ptp(saturated[0, 0]) > np.ptp(red[0, 0]) > np.ptp(desaturated[0, 0])
    analysis["hsl"][0].update({"saturation": 0, "luminance": 100})
    assert op.apply_numpy(red, op.resolve(analysis)).max() > red.max()
    analysis["hsl"][0]["luminance"] = -100
    assert op.apply_numpy(red, op.resolve(analysis)).max() < red.max()


def test_hsl_nonzero_hue_follows_direction_and_legacy(sample_analysis):
    arr = np.asarray([[[1.0, 0.2, 0.2]]], dtype=np.float32)
    outputs = {}
    for hue in (-30, 30):
        analysis = _zero(sample_analysis)
        analysis["hsl"] = [
            {"color": "red", "hue": hue, "saturation": 0, "luminance": 0}
        ]
        expected = _legacy._apply_color_ops(arr.copy(), analysis)
        actual = pipeline.apply_color_ops_numpy(arr.copy(), analysis)
        assert np.max(np.abs(actual - expected)) <= 1.0 / 255
        outputs[hue] = _legacy._rgb_to_hsv(actual)[0, 0, 0]
    assert outputs[30] < 180 < outputs[-30]


def test_saturation_operator_directions_and_zero(sample_analysis):
    from looklift.render.operators.color import Saturation

    op = Saturation()
    analysis = _zero(sample_analysis)
    assert op.resolve(analysis) is None
    arr = np.asarray([[[0.8, 0.4, 0.2]]], np.float32)
    analysis["basic"]["saturation"] = 50
    more = op.apply_numpy(arr, op.resolve(analysis))
    analysis["basic"]["saturation"] = -50
    less = op.apply_numpy(arr, op.resolve(analysis))
    assert np.ptp(more[0, 0]) > np.ptp(arr[0, 0]) > np.ptp(less[0, 0])
    analysis["basic"]["saturation"] = 0
    analysis["basic"]["vibrance"] = 100
    assert np.ptp(op.apply_numpy(arr, op.resolve(analysis))[0, 0]) > np.ptp(arr[0, 0])


def test_color_grading_operator_directions_zero_and_contract_only(sample_analysis):
    from looklift.render.operators.color import ColorGrading

    op = ColorGrading()
    analysis = _zero(sample_analysis)
    assert op.resolve(analysis) is None
    analysis["color_grading"]["global_"]["luminance"] = 100
    assert op.apply_numpy(_gray(), op.resolve(analysis)).mean() > 0.5
    analysis["color_grading"]["global_"]["luminance"] = -100
    assert op.apply_numpy(_gray(), op.resolve(analysis)).mean() < 0.5
    analysis["color_grading"]["global_"] = {"hue": 0, "saturation": 50, "luminance": 0}
    baseline = op.apply_numpy(_gray(), op.resolve(analysis))
    analysis["color_grading"]["blending"] = 0
    analysis["color_grading"]["balance"] = 100
    changed = op.apply_numpy(_gray(), op.resolve(analysis))
    np.testing.assert_array_equal(changed, baseline)


def test_color_grading_nonzero_tint_changes_pixels_and_matches_legacy(sample_analysis):
    analysis = _zero(sample_analysis)
    analysis["color_grading"]["global_"] = {
        "hue": 210,
        "saturation": 50,
        "luminance": 0,
    }
    arr = _gray()
    expected = _legacy._apply_color_ops(arr.copy(), analysis)
    actual = pipeline.apply_color_ops_numpy(arr.copy(), analysis)
    assert not np.array_equal(actual, arr)
    assert np.max(np.abs(actual - expected)) <= 1.0 / 255


def test_zero_analysis_pipeline_is_exact_float32_identity_without_mutation(
    sample_analysis,
):
    analysis = _zero(sample_analysis)
    arr = np.asarray(
        [[[0.0, 0.25, 1.0], [1.0, 0.5, 0.0]]],
        dtype=np.float32,
    )
    before = arr.copy()
    actual = pipeline.apply_color_ops_numpy(arr, analysis)
    np.testing.assert_array_equal(actual, before)
    np.testing.assert_array_equal(arr, before)
    assert actual.dtype == np.float32


def test_registry_order_domains_and_resolved_leaf_contract(sample_analysis):
    from looklift.render.base import Domain, OP_BITS, Stage
    from looklift.render.operators import REGISTRY

    names = [op.name for op in REGISTRY]
    assert names == sorted(names, key=lambda name: OP_BITS[name])
    assert all(
        op.stage is (Stage.OUTPUT if op.name in {"vignette", "grain"} else Stage.FUSED)
        for op in REGISTRY
    )
    assert {
        op.name for op in REGISTRY if op.domain is Domain.LINEAR
    } == {"exposure", "white_balance"}
    assert all(
        op.domain is Domain.DISPLAY
        for op in REGISTRY
        if op.name not in {"exposure", "white_balance"}
    )
    resolved = pipeline.resolve_params(sample_analysis)
    assert all(
        resolved.get(name) is None or isinstance(resolved.get(name), tuple)
        for name in names
    )
