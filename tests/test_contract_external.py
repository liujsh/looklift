import inspect

import numpy as np
from PIL import Image

from looklift import intensity, render


def _analysis():
    return {
        "basic": {
            "temperature_shift": 20,
            "tint_shift": 0,
            "exposure": 0.8,
            "contrast": 20,
            "highlights": 0,
            "shadows": 0,
            "whites": 0,
            "blacks": 0,
            "texture": 0,
            "clarity": 0,
            "dehaze": 0,
            "vibrance": 0,
            "saturation": 15,
        },
        "tone_curve": [],
        "hsl": [],
        "color_grading": {},
        "effects": {"vignette_amount": 0, "grain_amount": 0},
    }


def test_render_signature_type_size_and_default_icc():
    assert tuple(inspect.signature(render.render).parameters) == ("image", "analysis")
    image = Image.new("RGB", (48, 32), (128, 128, 128))
    output = render.render(image, _analysis())
    assert isinstance(output, Image.Image)
    assert output.size == image.size
    assert output.info.get("icc_profile")


def test_score_signature_and_return_type_unchanged():
    assert tuple(inspect.signature(render.score).parameters) == ("rendered", "target")
    image = Image.new("RGB", (32, 32), (100, 100, 100))
    assert isinstance(render.score(image, image), float)


def test_intensity_factor_zero_is_near_original():
    image = Image.new("RGB", (32, 32), (128, 100, 90))
    output = render.render(image, intensity.scale_analysis(_analysis(), 0.0))
    delta = np.abs(np.asarray(output, np.float32) - np.asarray(image, np.float32))
    assert delta.mean() < 3.0


def test_intensity_factor_one_equals_full_effect():
    image = Image.new("RGB", (32, 32), (128, 100, 90))
    scaled = render.render(image, intensity.scale_analysis(_analysis(), 1.0))
    direct = render.render(image, _analysis())
    np.testing.assert_array_equal(np.asarray(scaled), np.asarray(direct))
