from io import BytesIO

from PIL import Image

from looklift import render
from looklift.render import color_space as cs
from looklift.render import pipeline


def _analysis():
    return {
        "basic": {},
        "tone_curve": [],
        "hsl": [],
        "color_grading": {},
        "effects": {},
    }


def test_render_result_has_default_srgb_icc():
    output = render.render(Image.new("RGB", (16, 16)), _analysis())
    assert output.info["icc_profile"] == cs.srgb_icc_bytes()


def test_pipeline_export_reopens_with_srgb_icc(tmp_path):
    path = tmp_path / "output.jpg"
    returned = pipeline.export(Image.new("RGB", (16, 16)), _analysis(), path)
    assert returned == path
    with Image.open(path) as reopened:
        assert reopened.info["icc_profile"] == cs.srgb_icc_bytes()


def test_pillow_export_keeps_icc_when_pyvips_is_unavailable(tmp_path, monkeypatch):
    monkeypatch.setattr(cs, "HAS_PYVIPS", False)
    path = tmp_path / "fallback.jpg"
    pipeline.export(Image.new("RGB", (8, 8)), _analysis(), path)
    with Image.open(path) as reopened:
        assert reopened.info["icc_profile"] == cs.srgb_icc_bytes()


def test_icc_survives_explicit_jpeg_bytes_save():
    output = pipeline.render(Image.new("RGB", (8, 8)), _analysis())
    buffer = BytesIO()
    output.save(
        buffer,
        format="JPEG",
        icc_profile=output.info["icc_profile"],
    )
    with Image.open(BytesIO(buffer.getvalue())) as reopened:
        assert reopened.info["icc_profile"] == cs.srgb_icc_bytes()
