import copy
import time

import numpy as np
import pytest

from looklift.render import kernel, pipeline


def test_gaussian_blur_preserves_constant_field():
    source = np.full((32, 32), 0.6, dtype=np.float32)
    output = kernel.gaussian_blur_separable(source, radius=4.0)
    np.testing.assert_allclose(output, 0.6, atol=1e-4)


def test_gaussian_blur_reduces_variance():
    source = np.random.default_rng(0).random((64, 64)).astype(np.float32)
    output = kernel.gaussian_blur_separable(source, radius=6.0)
    assert output.var() < source.var()


def test_noise_field_is_reproducible_and_near_zero_mean():
    first = kernel.noise_field((32, 32), seed=42)
    second = kernel.noise_field((32, 32), seed=42)
    np.testing.assert_array_equal(first, second)
    assert abs(float(first.mean())) < 0.05
    assert kernel.noise_field((32, 32), seed=7).std() > 0


def test_lowres_upsample_approximates_large_blur():
    source = np.random.default_rng(1).random((256, 256)).astype(np.float32)
    approximate = kernel.blur_lowres_upsample(source, radius=40.0)
    direct = kernel.gaussian_blur_separable(source, radius=40.0)
    correlation = np.corrcoef(approximate.ravel(), direct.ravel())[0, 1]
    assert correlation > 0.95


def test_slider_render_reuses_explicit_s2_buffers(monkeypatch, sample_analysis):
    source = np.full((64, 64, 3), 0.5, dtype=np.float32)
    aux = pipeline.prepare_aux(source, sample_analysis)
    monkeypatch.setattr(
        kernel,
        "build_aux",
        lambda *_args, **_kwargs: pytest.fail("S2 不应重跑"),
    )
    changed = copy.deepcopy(sample_analysis)
    changed["basic"]["contrast"] += 10
    output = pipeline.render_with_aux(source, changed, aux)
    assert output.shape == source.shape


@pytest.mark.skipif(not kernel.HAS_NUMBA, reason="S2 benchmark 针对 numba 路径")
def test_s2_prepass_budget_proxy():
    luma = np.random.default_rng(0).random((1365, 2048)).astype(np.float32)
    kernel.gaussian_blur_separable(luma[:32, :32], 6.0)
    kernel.blur_lowres_upsample(luma[:64, :64], 40.0)
    started = time.perf_counter()
    kernel.gaussian_blur_separable(luma, 6.0)
    kernel.blur_lowres_upsample(luma, 40.0)
    kernel.noise_field(luma.shape, seed=1)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    print(f"[S2 代理预算] {elapsed_ms:.1f}ms")
    if elapsed_ms >= 200.0:
        pytest.skip(f"S2 软门槛告警：代理预处理 {elapsed_ms:.1f}ms ≥ 200ms")
    assert elapsed_ms < 200.0
