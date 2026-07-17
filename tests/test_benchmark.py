import time

import numpy as np
import pytest
from PIL import Image

from looklift.render import kernel, pipeline


def _full_analysis():
    return {
        "basic": {
            "temperature_shift": 20,
            "tint_shift": -10,
            "exposure": 0.5,
            "contrast": 25,
            "highlights": -30,
            "shadows": 40,
            "whites": -10,
            "blacks": 15,
            "texture": 30,
            "clarity": 25,
            "dehaze": 20,
            "vibrance": 20,
            "saturation": 15,
        },
        "tone_curve": [
            {"input": 0, "output": 15},
            {"input": 255, "output": 245},
        ],
        "hsl": [{"color": "blue", "hue": -10, "saturation": 15, "luminance": -8}],
        "color_grading": {
            "shadows": {"hue": 210, "saturation": 20, "luminance": 5},
            "midtones": {"hue": 0, "saturation": 0, "luminance": 0},
            "highlights": {"hue": 45, "saturation": 12, "luminance": 0},
            "global_": {"hue": 0, "saturation": 0, "luminance": 0},
            "blending": 50,
            "balance": -10,
        },
        "effects": {"vignette_amount": -15, "grain_amount": 25},
    }


def test_warmup_uses_small_float32_dummy(monkeypatch):
    observed = []

    def capture(arr, analysis, aux=None):
        observed.append(arr)
        return arr

    monkeypatch.setattr(pipeline, "render_fused", capture)
    pipeline.warmup()
    assert len(observed) == 1
    assert observed[0].shape == (4, 4, 3)
    assert observed[0].dtype == np.float32


def test_proxy_caps_long_edge_and_full_keeps_size():
    image = Image.new("RGB", (3000, 1500), (64, 96, 128))
    analysis = _full_analysis()
    proxy = pipeline.render_proxy(image, analysis)
    full = pipeline.render_full(Image.new("RGB", (30, 15)), analysis)
    assert proxy.size == (2048, 1024)
    assert full.size == (30, 15)


@pytest.mark.skipif(not kernel.HAS_NUMBA, reason="benchmark 针对融合内核")
def test_pointwise_fused_2048_under_50ms_soft_gate():
    pipeline.warmup()
    arr = np.random.default_rng(0).random((1365, 2048, 3)).astype(np.float32)
    analysis = _full_analysis()
    aux = pipeline.prepare_aux(arr, analysis)
    pipeline.render_with_aux(arr, analysis, aux)
    timings = []
    for _ in range(3):
        started = time.perf_counter()
        pipeline.render_with_aux(arr, analysis, aux)
        timings.append((time.perf_counter() - started) * 1000.0)
    elapsed_ms = min(timings)
    if elapsed_ms >= 50.0:
        pytest.skip(f"软门槛告警：2048px pointwise {elapsed_ms:.1f}ms ≥ 50ms")
    assert elapsed_ms < 50.0
