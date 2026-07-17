import inspect

import numpy as np
from PIL import Image

from looklift import render
from looklift.render import kernel, pipeline
from looklift.render.operators.effects import Grain, Vignette, noise_aux


def _gray(value=0.5, size=(64, 64)):
    return np.full((*size, 3), value, dtype=np.float32)


def _analysis(grain=0, vignette=0):
    return {
        "basic": {},
        "tone_curve": [],
        "hsl": [],
        "color_grading": {},
        "effects": {"grain_amount": grain, "vignette_amount": vignette},
    }


def test_effect_zero_values_disable_both_ops():
    assert Grain().resolve(_analysis()) is None
    assert Vignette().resolve(_analysis()) is None


def test_grain_increases_variance_and_reuses_fixed_noise():
    source = _gray()
    noise = kernel.noise_field(source.shape[:2], seed=42)
    params = Grain().resolve(_analysis(grain=60))
    first = Grain().apply_numpy(source, params, noise_aux(noise))
    second = Grain().apply_numpy(source, params, noise_aux(noise))
    assert first.var() > source.var()
    np.testing.assert_array_equal(first, second)


def test_grain_is_strongest_in_midtones():
    noise = kernel.noise_field((64, 64), seed=7)
    params = Grain().resolve(_analysis(grain=100))
    mid = Grain().apply_numpy(_gray(0.5), params, noise_aux(noise))
    high = Grain().apply_numpy(_gray(0.98), params, noise_aux(noise))
    assert np.abs(mid - 0.5).std() > np.abs(high - 0.98).std()


def test_vignette_darkens_corners_more_than_center():
    params = Vignette().resolve(_analysis(vignette=-80))
    output = Vignette().apply_numpy(_gray(), params)
    assert output[0, 0].mean() < output[32, 32].mean() - 0.05


def test_public_render_calls_unique_grain_overlay_once(monkeypatch):
    calls = []
    real = pipeline.apply_output_grain

    def counted(*args, **kwargs):
        calls.append(1)
        return real(*args, **kwargs)

    monkeypatch.setattr(pipeline, "apply_output_grain", counted)
    render.render(Image.new("RGB", (32, 32), (128, 128, 128)), _analysis(grain=40))
    assert calls == [1]


def test_numpy_and_fused_share_single_s4_grain_result():
    source = _gray(size=(32, 32))
    analysis = _analysis(grain=50)
    resolved = pipeline.resolve_params(analysis)
    aux = pipeline.prepare_aux(source, analysis)
    numpy_base = pipeline.render_arr(source, analysis, aux)
    fused_base = pipeline.render_fused(source, analysis, aux)
    numpy_output = pipeline.apply_output_effects(numpy_base, resolved, aux)
    fused_output = pipeline.apply_output_effects(fused_base, resolved, aux)
    assert np.max(np.abs(numpy_output - fused_output)) <= 1.0 / 255
    source_text = inspect.getsource(kernel.fused.py_func)
    assert "grain" not in source_text and "noise" not in source_text
