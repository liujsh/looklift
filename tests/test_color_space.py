from io import BytesIO

import numpy as np
import pytest
from PIL import ImageCms

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


def test_srgb_to_linear_negative_values_do_not_evaluate_power_branch():
    values = np.array([-0.1, -0.055, -1.0], dtype=np.float32)

    with np.errstate(invalid="raise"):
        converted = cs.srgb_to_linear(values)

    np.testing.assert_allclose(converted, values / 12.92, rtol=0.0, atol=1e-7)


def test_linear_to_srgb_preserves_highlights_and_input():
    values = np.array([2.0], dtype=np.float32)
    original = values.copy()

    converted = cs.linear_to_srgb(values)

    assert converted[0] > 1.0
    np.testing.assert_array_equal(values, original)


def test_eotf_threshold_and_neighbors_follow_piecewise_formula():
    threshold = np.float32(0.04045)
    below = np.nextafter(threshold, np.float32(-np.inf))
    above = np.nextafter(threshold, np.float32(np.inf))
    values = np.array([below, threshold, above], dtype=np.float32)

    converted = cs.srgb_to_linear(values)
    expected = np.array(
        [
            float(below) / 12.92,
            float(threshold) / 12.92,
            ((float(above) + 0.055) / 1.055) ** 2.4,
        ],
        dtype=np.float32,
    )

    np.testing.assert_allclose(converted, expected, rtol=1e-6, atol=1e-8)
    assert np.max(np.abs(np.diff(converted))) < 1e-6


def test_oetf_threshold_and_neighbors_follow_piecewise_formula():
    threshold = np.float32(0.0031308)
    below = np.nextafter(threshold, np.float32(-np.inf))
    above = np.nextafter(threshold, np.float32(np.inf))
    values = np.array([below, threshold, above], dtype=np.float32)

    converted = cs.linear_to_srgb(values)
    expected = np.array(
        [
            float(below) * 12.92,
            float(threshold) * 12.92,
            1.055 * float(above) ** (1.0 / 2.4) - 0.055,
        ],
        dtype=np.float32,
    )

    np.testing.assert_allclose(converted, expected, rtol=1e-6, atol=1e-8)
    assert np.max(np.abs(np.diff(converted))) < 1e-6


@pytest.mark.parametrize("convert", [cs.srgb_to_linear, cs.linear_to_srgb])
def test_transfer_functions_preserve_shape_propagate_nan_and_return_float32(convert):
    values = np.array([[0.0, np.nan], [0.25, 2.0]], dtype=np.float64)

    converted = convert(values)

    assert converted.shape == values.shape
    assert converted.dtype == np.float32
    assert np.isnan(converted[0, 1])


def test_srgb_icc_header_and_pillow_parse_are_valid():
    profile_bytes = cs.srgb_icc_bytes()

    assert int.from_bytes(profile_bytes[:4], byteorder="big") == len(profile_bytes)
    assert profile_bytes[36:40] == b"acsp"
    profile = ImageCms.ImageCmsProfile(BytesIO(profile_bytes))
    assert "srgb" in profile.profile.profile_description.casefold()
