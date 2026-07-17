import copy

import numpy as np
import pytest

from looklift.render.base import Domain, OP_BITS, Operator, ResolvedParams, Stage


class _StubOp:
    name = "stub"
    stage = Stage.FUSED
    domain = Domain.DISPLAY

    def resolve(self, analysis):
        value = analysis.get("basic", {}).get("exposure", 0)
        if not value:
            return None  # 全 0 → enable=False
        return (float(value),)

    def apply_numpy(self, arr, params, aux=None):
        (gain,) = params
        return arr * gain

    def apply_px(self, r, g, b, *params, aux=None):
        (gain,) = params
        return r * gain, g * gain, b * gain


def test_operator_runtime_protocol_and_both_apply_forms():
    op = _StubOp()
    assert isinstance(op, Operator)
    arr = np.asarray([[[0.1, 0.2, 0.3]]], dtype=np.float32)
    assert np.allclose(op.apply_numpy(arr, (2.0,)), arr * 2.0)
    assert op.apply_px(0.1, 0.2, 0.3, 2.0) == (0.2, 0.4, 0.6)


def test_resolve_zero_returns_none():
    assert _StubOp().resolve({"basic": {"exposure": 0}}) is None


def test_resolve_nonzero_returns_param_tuple():
    assert _StubOp().resolve({"basic": {"exposure": 1.5}}) == (1.5,)


def test_resolved_params_pack_sets_enable_bits_and_round_trips_valid_leaves():
    hsl = np.arange(24, dtype=np.float32)
    params = ResolvedParams.pack(
        {
            "exposure": (2.0, np.float32(0.5), np.int64(3)),
            "hsl": (hsl,),
            "contrast": None,
        }
    )
    assert params.is_enabled("exposure")
    assert params.is_enabled("hsl")
    assert not params.is_enabled("contrast")
    assert params.get("exposure") == (2.0, np.float32(0.5), np.int64(3))
    assert params.get("hsl")[0] is hsl


@pytest.mark.parametrize(
    "bad_leaf",
    [
        [1.0],
        {1.0},
        {"hue": 30.0},
        object(),
        (1.0,),
        np.array([1.0], dtype=object),
        np.zeros((2, 2), dtype=np.float32),
        np.zeros(2, dtype=np.float64),
        np.arange(4, dtype=np.float32)[::2],
    ],
)
def test_resolved_params_rejects_invalid_leaf_types(bad_leaf):
    with pytest.raises(TypeError):
        ResolvedParams.pack({"hsl": (bad_leaf,)})


def test_resolved_params_rejects_non_tuple_result():
    with pytest.raises(TypeError):
        ResolvedParams.pack({"exposure": [1.0]})


def test_resolved_params_pack_failure_is_atomic_and_keeps_input_unchanged():
    class _TrackingResolvedParams(ResolvedParams):
        created = 0

        def __init__(self):
            type(self).created += 1
            super().__init__()

    op_results = {
        "exposure": (2.0,),
        "hsl": ([1.0],),  # 后置非法叶，确保前项已可通过验证
    }
    original = copy.deepcopy(op_results)

    with pytest.raises(TypeError):
        _TrackingResolvedParams.pack(op_results)

    assert _TrackingResolvedParams.created == 0
    assert op_results == original


def test_op_bits_exact_stable_mapping_and_single_bits():
    names = (
        "exposure",
        "white_balance",
        "contrast",
        "highlights_shadows",
        "whites_blacks",
        "tone_curve",
        "hsl",
        "saturation",
        "color_grading",
        "texture",
        "clarity",
        "dehaze",
        "vignette",
        "grain",
    )
    assert OP_BITS == {name: 1 << i for i, name in enumerate(names)}
    assert all(bit > 0 and bit & (bit - 1) == 0 for bit in OP_BITS.values())
