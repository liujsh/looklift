"""使用主渲染引擎生成不覆盖已有文件的自动化 JPEG。"""
from __future__ import annotations

import os
import uuid
from pathlib import Path

from PIL import Image, ImageOps

from . import intensity, render


def render_automation_jpeg(
    source: Path,
    output: Path,
    analysis: dict,
    factor: float,
    quality: int,
) -> None:
    """完整尺寸渲染到同目录临时文件，再以硬链接原子创建最终文件。"""
    if output.exists():
        raise FileExistsError(f"输出文件已存在：{output}")
    with Image.open(source) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
    rendered = render.render(image, intensity.scale_analysis(analysis, factor))
    temporary = output.with_name(f".{output.name}.{uuid.uuid4().hex}.tmp")
    options: dict[str, object] = {"format": "JPEG", "quality": quality}
    if rendered.info.get("icc_profile"):
        options["icc_profile"] = rendered.info["icc_profile"]
    try:
        rendered.save(temporary, **options)
        # 临时文件和输出位于同一目录；硬链接创建在 Windows/NTFS 上不会覆盖已有文件。
        os.link(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
