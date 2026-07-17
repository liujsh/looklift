import numpy as np
import pytest

from looklift.render import color_space as cs


def test_srgb_linear_roundtrip_under_1e5():
    rng = np.random.default_rng(0)
    arr = rng.random((64, 64, 3)).astype(np.float32)
    back = cs.linear_to_srgb(cs.srgb_to_linear(arr))
    assert np.max(np.abs(back - arr)) < 1e-5


def test_midgray_display_maps_to_known_linear():
    # 精确 sRGB EOTF：((0.5 + 0.055) / 1.055) ** 2.4 ≈ 0.21404
    lin = cs.srgb_to_linear(np.array([0.5], dtype=np.float32))
    assert lin[0] == pytest.approx(0.21404, abs=1e-4)


def test_linear_light_doubling_is_physical():
    # linear 域 ×2 就是 ×2（物理正确）；这是 exposure +1 EV 的地基
    lin = cs.srgb_to_linear(np.array([0.25], dtype=np.float32))
    assert cs.linear_to_srgb(lin * 2.0)[0] == pytest.approx(
        cs.linear_to_srgb(np.array([lin[0] * 2.0], dtype=np.float32))[0], abs=1e-6
    )


def test_low_segment_uses_linear_slope():
    # 暗部走线性段 c / 12.92，不走 gamma
    assert cs.srgb_to_linear(np.array([0.02], dtype=np.float32))[0] == pytest.approx(
        0.02 / 12.92, abs=1e-7
    )


def test_srgb_icc_bytes_nonempty():
    assert len(cs.srgb_icc_bytes()) > 0


def test_embed_icc_falls_back_to_pillow_when_no_pyvips(monkeypatch):
    monkeypatch.setattr(cs, "HAS_PYVIPS", False)
    from PIL import Image

    kwargs = cs.embed_icc(Image.new("RGB", (4, 4)))
    assert kwargs["icc_profile"] == cs.srgb_icc_bytes()
