import pytest


@pytest.fixture
def sample_analysis():
    return {
        "summary": "测试风格",
        "steps": ["步骤一", "步骤二"],
        "basic": {
            "temperature_shift": 12, "tint_shift": -5, "exposure": 0.35,
            "contrast": 18, "highlights": -40, "shadows": 30, "whites": -10,
            "blacks": 15, "texture": 5, "clarity": 8, "dehaze": 0,
            "vibrance": 15, "saturation": -8,
        },
        "tone_curve": [
            {"input": 0, "output": 18}, {"input": 64, "output": 60},
            {"input": 192, "output": 200}, {"input": 255, "output": 245},
        ],
        "hsl": [
            {"color": "orange", "hue": -6, "saturation": -10, "luminance": 8},
            {"color": "blue", "hue": -15, "saturation": 12, "luminance": -10},
        ],
        "color_grading": {
            "shadows": {"hue": 210, "saturation": 18, "luminance": 0},
            "midtones": {"hue": 0, "saturation": 0, "luminance": 0},
            "highlights": {"hue": 45, "saturation": 10, "luminance": 0},
            "global_": {"hue": 0, "saturation": 0, "luminance": 0},
            "blending": 50, "balance": -10,
        },
        "effects": {"vignette_amount": -12, "grain_amount": 20},
    }
