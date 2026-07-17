import numpy as np
import pytest
from PIL import Image

from looklift import render
from looklift.render import kernel, pipeline
from looklift.render.base import OP_BITS, ResolvedParams


EXPECTED_RENDER_PARAM_LAYOUT = (
    ("enable", "int64", ()),
    ("exposure", "float32", ()),
    ("white_balance", "float32", (2,)),
    ("contrast", "float32", ()),
    ("highlights_shadows", "float32", (2,)),
    ("whites_blacks", "float32", (2,)),
    ("tone_curve_lut", "float32", (1024,)),
    ("hsl", "float32", (24,)),
    ("saturation", "float32", (2,)),
    ("color_grading", "float32", (12,)),
    ("texture", "float32", ()),
    ("clarity", "float32", ()),
    ("dehaze", "float32", ()),
)


def _analysis(**basic):
    values = {
        "temperature_shift": 0,
        "tint_shift": 0,
        "exposure": 0,
        "contrast": 0,
        "highlights": 0,
        "shadows": 0,
        "whites": 0,
        "blacks": 0,
        "texture": 0,
        "clarity": 0,
        "dehaze": 0,
        "vibrance": 0,
        "saturation": 0,
    }
    values.update(basic)
    return {
        "basic": values,
        "tone_curve": [],
        "hsl": [],
        "color_grading": {
            zone: {"hue": 0, "saturation": 0, "luminance": 0}
            for zone in ("shadows", "midtones", "highlights", "global_")
        }
        | {"blending": 50, "balance": 0},
        "effects": {"vignette_amount": 0, "grain_amount": 0},
    }


def _all_active_analysis():
    analysis = _analysis(
        exposure=0.5,
        temperature_shift=20,
        tint_shift=-10,
        contrast=15,
        highlights=-25,
        shadows=30,
        whites=12,
        blacks=-8,
        saturation=18,
        vibrance=9,
    )
    analysis["tone_curve"] = [
        {"input": 0, "output": 10},
        {"input": 128, "output": 150},
        {"input": 255, "output": 245},
    ]
    analysis["hsl"] = [
        {"color": "blue", "hue": -8, "saturation": 14, "luminance": 6}
    ]
    analysis["color_grading"]["shadows"] = {
        "hue": 210,
        "saturation": 20,
        "luminance": 5,
    }
    return analysis


def test_render_param_layout_exact_and_each_field_type_shape():
    assert kernel.RENDER_PARAM_LAYOUT == EXPECTED_RENDER_PARAM_LAYOUT
    params = pipeline.marshal_render_params(
        pipeline.resolve_params(_analysis(exposure=0.5))
    )
    assert params._fields == tuple(row[0] for row in EXPECTED_RENDER_PARAM_LAYOUT)
    assert isinstance(params.enable, (int, np.integer))
    for name, dtype, shape in EXPECTED_RENDER_PARAM_LAYOUT[1:]:
        value = getattr(params, name)
        if shape:
            assert isinstance(value, np.ndarray)
            assert value.dtype == np.dtype(dtype)
            assert value.shape == shape
            assert value.flags.c_contiguous
        else:
            assert isinstance(value, np.float32)


def test_active_marshal_preserves_every_field_exactly():
    resolved = pipeline.resolve_params(_all_active_analysis())
    params = pipeline.marshal_render_params(resolved)
    active = (
        "exposure",
        "white_balance",
        "contrast",
        "highlights_shadows",
        "whites_blacks",
        "tone_curve",
        "hsl",
        "saturation",
        "color_grading",
    )
    assert params.enable == resolved.enable == sum(OP_BITS[name] for name in active)
    assert params.exposure == np.float32(resolved.get("exposure")[0])
    np.testing.assert_array_equal(params.white_balance, resolved.get("white_balance"))
    assert params.contrast == np.float32(resolved.get("contrast")[0])
    np.testing.assert_array_equal(
        params.highlights_shadows, resolved.get("highlights_shadows")
    )
    np.testing.assert_array_equal(params.whites_blacks, resolved.get("whites_blacks"))
    np.testing.assert_array_equal(params.tone_curve_lut, resolved.get("tone_curve")[0])
    np.testing.assert_array_equal(params.hsl, resolved.get("hsl")[0])
    np.testing.assert_array_equal(params.saturation, resolved.get("saturation"))
    np.testing.assert_array_equal(params.color_grading, resolved.get("color_grading")[0])


def test_disabled_fields_are_typed_contiguous_zero_values():
    params = pipeline.marshal_render_params(ResolvedParams.pack({}))
    assert params.enable == 0
    for name, _, shape in EXPECTED_RENDER_PARAM_LAYOUT[1:]:
        value = getattr(params, name)
        assert value is not None
        assert not isinstance(value, (list, dict))
        if shape:
            assert value.shape == shape and value.flags.c_contiguous
            assert np.count_nonzero(value) == 0
        else:
            assert value == np.float32(0)


@pytest.mark.skipif(not kernel.HAS_NUMBA, reason="numba 缺失走 numpy 兜底")
def test_numba_kernel_accepts_only_render_params_record():
    resolved = pipeline.resolve_params(_analysis(exposure=0.5))
    params = pipeline.marshal_render_params(resolved)
    assert kernel.probe_render_params(params) == params.enable
    assert kernel.probe_render_params.nopython_signatures
    with pytest.raises(Exception):
        kernel.probe_render_params(resolved)


@pytest.mark.skipif(not kernel.HAS_NUMBA, reason="numba 缺失走 numpy 兜底")
def test_fused_enables_parallel_fastmath_and_disk_cache():
    assert kernel.fused.targetoptions["parallel"] is True
    assert kernel.fused.targetoptions["fastmath"] is True
    assert kernel.fused._cache is not None


@pytest.mark.skipif(not kernel.HAS_NUMBA, reason="numba 缺失走 numpy 兜底")
def test_fused_matches_numpy_reference_with_all_pointwise_ops():
    src = np.random.default_rng(0).random((32, 32, 3)).astype(np.float32)
    analysis = _all_active_analysis()
    expected = pipeline.render_arr(src.copy(), analysis)
    actual = pipeline.render_fused(src.copy(), analysis)
    assert np.max(np.abs(actual - expected)) <= 1.0 / 255


@pytest.mark.skipif(not kernel.HAS_NUMBA, reason="numba 缺失走 numpy 兜底")
def test_disabled_ops_are_noop_in_fused():
    src = np.random.default_rng(1).random((16, 16, 3)).astype(np.float32)
    actual = pipeline.render_fused(src.copy(), _analysis())
    assert np.max(np.abs(actual - src)) <= 1.0 / 255


def test_numpy_fallback_when_numba_absent(monkeypatch):
    src = np.full((8, 8, 3), 0.3, dtype=np.float32)
    analysis = _analysis(exposure=1.0)
    monkeypatch.setattr(kernel, "HAS_NUMBA", False)
    actual = pipeline.render_fused(src.copy(), analysis)
    expected = pipeline.render_arr(src.copy(), analysis)
    np.testing.assert_allclose(actual, expected, atol=1e-6)


def test_numpy_fallback_when_numba_compile_fails(monkeypatch):
    src = np.full((4, 4, 3), 0.3, dtype=np.float32)
    analysis = _analysis(exposure=1.0)

    def fail(*args, **kwargs):
        raise kernel.NumbaError("模拟 JIT 不可用")

    monkeypatch.setattr(kernel, "fused", fail)
    actual = pipeline.render_fused(src.copy(), analysis)
    expected = pipeline.render_arr(src.copy(), analysis)
    np.testing.assert_allclose(actual, expected, atol=1e-6)


def test_public_render_routes_pointwise_work_through_fused(monkeypatch):
    calls = []

    def observe(arr, analysis, aux=None):
        calls.append((arr.shape, analysis))
        return arr

    monkeypatch.setattr(pipeline, "render_fused", observe)
    image = Image.new("RGB", (3, 2), (64, 64, 64))
    analysis = _analysis()

    output = render.render(image, analysis)

    assert output.size == image.size
    assert calls == [((2, 3, 3), analysis)]
