"""Shared current-effect preview rendering for the GUI and AI proxy."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageOps

from . import intensity, render


def render_preview_jpeg(
    image_path: Path,
    analysis: dict,
    factor: float,
    *,
    max_edge: int,
    quality: int,
    include_icc: bool = True,
) -> bytes:
    """Render a bounded JPEG from the same analysis/factor snapshot."""
    with Image.open(image_path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    image.thumbnail((max_edge, max_edge), Image.Resampling.LANCZOS)
    rendered = render.render(image, intensity.scale_analysis(analysis, factor))
    output = io.BytesIO()
    options: dict[str, object] = {"format": "JPEG", "quality": quality}
    if include_icc and rendered.info.get("icc_profile"):
        options["icc_profile"] = rendered.info["icc_profile"]
    rendered.save(output, **options)
    return output.getvalue()
