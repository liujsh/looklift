import numpy as np

from looklift.render.base import Domain, OP_BITS, RenderParams, Stage


class _StubOp:
    name = "stub"
    stage = Stage.FUSED
    domain = Domain.DISPLAY

    def resolve(self, analysis):
        v = analysis.get("basic", {}).get("exposure", 0)
        if not v:
            return None  # 全 0 → enable=False
        return (float(v),)

    def apply_numpy(self, arr, params, aux=None):
        (gain,) = params
        return arr * gain


def test_resolve_zero_returns_none():
    assert _StubOp().resolve({"basic": {"exposure": 0}}) is None


def test_resolve_nonzero_returns_param_tuple():
    assert _StubOp().resolve({"basic": {"exposure": 1.5}}) == (1.5,)


def test_render_params_pack_sets_enable_bits():
    params = RenderParams.pack({"exposure": (2.0,), "contrast": None})
    assert params.is_enabled("exposure")
    assert not params.is_enabled("contrast")
    assert params.get("exposure") == (2.0,)


def test_op_bits_unique_and_cover_all_ops():
    assert len(set(OP_BITS.values())) == len(OP_BITS)  # 位唯一
    assert "exposure" in OP_BITS and "grain" in OP_BITS
