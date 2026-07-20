"""v2.1 外部 AI 代理图与安全元数据白名单。"""
from __future__ import annotations

import base64
import io
from pathlib import Path

import pytest
from PIL import Image

from looklift.ai_proxy import prepare_ai_proxy, read_safe_image_info
from looklift.providers import MAX_EDGE, _encode_image


def _jpeg_with_exif(path: Path, size: tuple[int, int] = (3200, 1600)) -> None:
    exif = Image.Exif()
    exif[34855] = 400  # ISO
    exif[33434] = (1, 125)  # 快门
    exif[33437] = (28, 10)  # 光圈
    exif[37386] = (50, 1)  # 焦距
    exif[37380] = (-1, 3)  # 曝光补偿
    exif[41987] = 0  # 自动白平衡
    exif[40961] = 1  # sRGB
    exif[42033] = "BODY-SERIAL-SECRET"
    exif[315] = "PRIVATE ARTIST"
    exif[33432] = "PRIVATE COPYRIGHT"
    exif[270] = "PRIVATE FREE TEXT"
    Image.new("RGB", size, (80, 120, 160)).save(path, "JPEG", exif=exif, quality=94)


def test_proxy_is_rgb_jpeg_at_most_2048_and_contains_no_exif(tmp_path):
    source = tmp_path / "source.jpg"
    _jpeg_with_exif(source)

    with prepare_ai_proxy(source, include_metadata=True) as proxy:
        assert proxy.path.exists()
        with Image.open(proxy.path) as image:
            assert image.format == "JPEG"
            assert image.mode == "RGB"
            assert max(image.size) == 2048
            assert len(image.getexif()) == 0

    assert not proxy.path.exists()


def test_proxy_returns_only_safe_structured_metadata(tmp_path):
    source = tmp_path / "source.jpg"
    _jpeg_with_exif(source, (640, 480))

    with prepare_ai_proxy(source, include_metadata=True) as proxy:
        assert set(proxy.metadata) == {
            "iso",
            "shutter_seconds",
            "aperture",
            "focal_length_mm",
            "exposure_compensation_ev",
            "white_balance",
            "color_space",
        }
        assert proxy.metadata["iso"] == 400
        assert proxy.metadata["shutter_seconds"] == pytest.approx(1 / 125)
        assert proxy.metadata["aperture"] == pytest.approx(2.8)
        assert proxy.metadata["focal_length_mm"] == pytest.approx(50)
        assert proxy.metadata["exposure_compensation_ev"] == pytest.approx(-1 / 3)
        assert proxy.metadata["white_balance"] == "自动"
        assert proxy.metadata["color_space"] == "sRGB"
        serialized = repr(proxy.metadata)
        assert "SERIAL" not in serialized
        assert "ARTIST" not in serialized
        assert "COPYRIGHT" not in serialized
        assert "FREE TEXT" not in serialized


def test_safe_image_info_adds_format_without_exposing_identity_fields(tmp_path):
    source = tmp_path / "private-name.jpg"
    _jpeg_with_exif(source, (640, 480))

    info = read_safe_image_info(source)

    assert info["file_format"] == "JPEG"
    assert info["iso"] == 400
    serialized = repr(info)
    assert "private-name" not in serialized
    assert "SERIAL" not in serialized


def test_metadata_switch_returns_empty_object(tmp_path):
    source = tmp_path / "source.jpg"
    _jpeg_with_exif(source, (640, 480))

    with prepare_ai_proxy(source, include_metadata=False) as proxy:
        assert proxy.metadata == {}


def test_provider_reencode_keeps_proxy_bounded_and_does_not_restore_exif(tmp_path):
    source = tmp_path / "source.jpg"
    _jpeg_with_exif(source)

    with prepare_ai_proxy(source, include_metadata=True) as proxy:
        encoded, media_type = _encode_image(proxy.path)

    assert media_type == "image/jpeg"
    with Image.open(io.BytesIO(base64.b64decode(encoded))) as image:
        assert max(image.size) <= MAX_EDGE
        assert len(image.getexif()) == 0


def test_proxy_pixels_reflect_current_analysis_and_factor(tmp_path, sample_analysis):
    source = tmp_path / "source.jpg"
    Image.new("RGB", (640, 480), (70, 70, 70)).save(source, "JPEG", quality=95)
    current = dict(sample_analysis)
    current["basic"] = {**sample_analysis["basic"], "exposure": 2.0}

    with prepare_ai_proxy(
        source,
        analysis=current,
        factor=1.0,
        include_metadata=False,
    ) as proxy:
        with Image.open(proxy.path) as rendered:
            rendered_mean = sum(rendered.resize((1, 1)).getpixel((0, 0))) / 3

    with prepare_ai_proxy(
        source,
        analysis=current,
        factor=0.0,
        include_metadata=False,
    ) as proxy:
        with Image.open(proxy.path) as neutral:
            neutral_mean = sum(neutral.resize((1, 1)).getpixel((0, 0))) / 3

    assert rendered_mean > neutral_mean + 25
