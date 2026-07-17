import copy

import numpy as np
from PIL import Image

from looklift import render
from looklift.render import pipeline
from looklift.render.operators.detail import Clarity, Texture
from looklift.render._legacy import _rgb_to_hsv
from looklift.render.operators.detail import Dehaze


def _edge_image(size=64):
    rng = np.random.default_rng(0)
    base = np.zeros((size, size, 3), dtype=np.float32)
    base[:, : size // 2] = 0.4
    base[:, size // 2 :] = 0.6
    texture = rng.normal(0, 0.02, base.shape).astype(np.float32)
    return np.clip(base + texture, 0, 1)


def _isolated_analysis(sample_analysis, **detail):
    analysis = copy.deepcopy(sample_analysis)
    analysis["basic"] = {key: 0 for key in analysis["basic"]}
    analysis["basic"].update(detail)
    analysis["tone_curve"] = []
    analysis["hsl"] = []
    analysis["color_grading"] = {}
    analysis["effects"] = {"vignette_amount": 0, "grain_amount": 0}
    return analysis


def _highpass_energy(arr):
    aux = pipeline.prepare_aux(arr, {})
    return float(((arr[..., 1] - aux.blur_mid) ** 2).mean())


def test_detail_zero_values_disable_both_ops():
    assert Texture().resolve({"basic": {"texture": 0}}) is None
    assert Clarity().resolve({"basic": {"clarity": 0}}) is None


def test_texture_positive_increases_midfrequency_energy(sample_analysis):
    source = _edge_image()
    analysis = _isolated_analysis(sample_analysis, texture=80)
    output = pipeline.render_arr(source, analysis)
    assert _highpass_energy(output) > _highpass_energy(source)


def test_clarity_prefers_midtones_over_extremes(sample_analysis):
    source = _edge_image()
    mid_analysis = _isolated_analysis(sample_analysis, clarity=80)
    mid_change = np.abs(pipeline.render_arr(source, mid_analysis) - source).mean()
    bright = np.clip(source + 0.38, 0, 1)
    bright_change = np.abs(pipeline.render_arr(bright, mid_analysis) - bright).mean()
    assert mid_change > bright_change


def test_detail_fused_matches_numpy_for_shared_aux(sample_analysis):
    source = _edge_image()
    analysis = _isolated_analysis(sample_analysis, texture=60, clarity=45)
    aux = pipeline.prepare_aux(source, analysis)
    expected = pipeline.render_arr(source, analysis, aux)
    actual = pipeline.render_fused(source, analysis, aux)
    assert np.max(np.abs(actual - expected)) <= 1.0 / 255


def test_texture_and_clarity_are_visible_through_public_render(sample_analysis):
    source = _edge_image(32)
    image = Image.fromarray((source * 255).astype(np.uint8), "RGB")
    zero = _isolated_analysis(sample_analysis)
    detailed = _isolated_analysis(sample_analysis, texture=80, clarity=60)
    baseline = np.asarray(render.render(image, zero))
    output = np.asarray(render.render(image, detailed))
    assert np.any(output != baseline)


def test_dehaze_positive_increases_hazy_contrast_and_saturation(sample_analysis):
    rng = np.random.default_rng(3)
    hazy = 0.5 + (rng.random((64, 64, 3)).astype(np.float32) - 0.5) * 0.08
    analysis = _isolated_analysis(sample_analysis, dehaze=80)
    output = pipeline.render_arr(hazy, analysis)
    assert output.std() > hazy.std()
    assert _rgb_to_hsv(output)[..., 1].mean() > _rgb_to_hsv(hazy)[..., 1].mean()


def test_dehaze_zero_disables_and_negative_adds_haze(sample_analysis):
    assert Dehaze().resolve({"basic": {"dehaze": 0}}) is None
    source = _edge_image()
    analysis = _isolated_analysis(sample_analysis, dehaze=-80)
    output = pipeline.render_arr(source, analysis)
    assert output.std() < source.std()
    assert _rgb_to_hsv(output)[..., 1].mean() < _rgb_to_hsv(source)[..., 1].mean()


def test_dehaze_fused_matches_numpy_for_shared_aux(sample_analysis):
    source = _edge_image()
    analysis = _isolated_analysis(sample_analysis, dehaze=65)
    aux = pipeline.prepare_aux(source, analysis)
    expected = pipeline.render_arr(source, analysis, aux)
    actual = pipeline.render_fused(source, analysis, aux)
    assert np.max(np.abs(actual - expected)) <= 1.0 / 255


def test_dehaze_is_visible_through_public_render(sample_analysis):
    source = _edge_image(32)
    image = Image.fromarray((source * 255).astype(np.uint8), "RGB")
    baseline = np.asarray(render.render(image, _isolated_analysis(sample_analysis)))
    positive = np.asarray(
        render.render(image, _isolated_analysis(sample_analysis, dehaze=70))
    )
    negative = np.asarray(
        render.render(image, _isolated_analysis(sample_analysis, dehaze=-70))
    )
    assert positive.std() > baseline.std() > negative.std()
