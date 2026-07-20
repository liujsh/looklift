"""生成外部 AI 可见的去元数据代理图和安全拍摄信息。"""
from __future__ import annotations

import math
import tempfile
from io import BytesIO
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from PIL import Image, ImageOps

from .preview import render_preview_jpeg

MAX_AI_PROXY_EDGE = 2048
_JPEG_QUALITY = 90

# 只读取明确允许的 EXIF tag；GPS、序列号、作者、版权和自由文本即使存在也
# 没有遍历入口，因此不会进入 provider 请求。
_SAFE_TAGS = {
    "iso": 34855,
    "shutter_seconds": 33434,
    "aperture": 33437,
    "focal_length_mm": 37386,
    "exposure_compensation_ev": 37380,
    "white_balance": 41987,
    "color_space": 40961,
}


@dataclass(frozen=True)
class AiProxy:
    path: Path
    metadata: dict[str, str | int | float]


def read_safe_image_info(source: Path) -> dict[str, str | int | float]:
    """Read only the local baseline fields approved for display/provider context."""
    with Image.open(Path(source)) as opened:
        metadata = _safe_metadata(opened.getexif())
        if opened.format:
            metadata["file_format"] = opened.format
    return metadata


@contextmanager
def prepare_ai_proxy(
    source: Path,
    *,
    analysis: dict | None = None,
    factor: float = 1.0,
    include_metadata: bool,
) -> Iterator[AiProxy]:
    """把当前效果重编码为最长边 2048px 的 RGB JPEG，退出时删除临时文件。"""
    source = Path(source)
    with Image.open(source) as opened:
        metadata = _safe_metadata(opened.getexif()) if include_metadata else {}
        image = ImageOps.exif_transpose(opened).convert("RGB") if analysis is None else None

    if analysis is None:
        assert image is not None
        image.thumbnail((MAX_AI_PROXY_EDGE, MAX_AI_PROXY_EDGE), Image.Resampling.LANCZOS)
    else:
        jpeg = render_preview_jpeg(
            source,
            analysis,
            factor,
            max_edge=MAX_AI_PROXY_EDGE,
            quality=_JPEG_QUALITY,
            include_icc=False,
        )
        image = Image.open(BytesIO(jpeg)).convert("RGB")

    with tempfile.TemporaryDirectory(prefix="looklift-ai-") as directory:
        proxy_path = Path(directory) / "proxy.jpg"
        # 不传 exif/icc_profile 等原图信息，确保输出是只含像素的重新编码文件。
        image.save(proxy_path, format="JPEG", quality=_JPEG_QUALITY, optimize=True)
        yield AiProxy(proxy_path, metadata)


def _safe_metadata(exif: Image.Exif) -> dict[str, str | int | float]:
    metadata: dict[str, str | int | float] = {}
    iso = _integer(exif.get(_SAFE_TAGS["iso"]))
    if iso is not None:
        metadata["iso"] = iso

    for key in (
        "shutter_seconds",
        "aperture",
        "focal_length_mm",
        "exposure_compensation_ev",
    ):
        value = _number(exif.get(_SAFE_TAGS[key]))
        if value is not None:
            metadata[key] = value

    white_balance = exif.get(_SAFE_TAGS["white_balance"])
    if white_balance in (0, 1):
        metadata["white_balance"] = "自动" if white_balance == 0 else "手动"

    color_space = exif.get(_SAFE_TAGS["color_space"])
    if color_space is not None:
        metadata["color_space"] = {
            1: "sRGB",
            2: "Adobe RGB",
            65535: "未校准",
        }.get(color_space, "其他")
    return metadata


def _integer(value: Any) -> int | None:
    number = _number(value)
    if number is None or not number.is_integer():
        return None
    return int(number)


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        if isinstance(value, tuple) and len(value) == 2:
            numerator, denominator = value
            number = float(numerator) / float(denominator)
        else:
            number = float(value)
    except (TypeError, ValueError, ZeroDivisionError):
        return None
    return number if math.isfinite(number) else None
