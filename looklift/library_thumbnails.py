"""图库缩略图生成：普通图片与可解码 RAW 共用受控缓存。"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps


@dataclass(frozen=True)
class ThumbnailResult:
    path: Path | None
    available: bool


class ThumbnailService:
    """优先解码源文件中的可用预览，失败时由界面展示格式占位卡。"""

    def __init__(self, directory: Path, max_edge: int = 512):
        self.directory = Path(directory)
        self.max_edge = max_edge

    def create(self, source: Path) -> ThumbnailResult:
        source = Path(source)
        try:
            with Image.open(source) as opened:
                image = ImageOps.exif_transpose(opened).convert("RGB")
                image.thumbnail((self.max_edge, self.max_edge), Image.Resampling.LANCZOS)
                self.directory.mkdir(parents=True, exist_ok=True)
                key = uuid.uuid5(uuid.NAMESPACE_URL, str(source.resolve()))
                target = self.directory / f"{key}.jpg"
                image.save(target, format="JPEG", quality=85, optimize=True)
        except (OSError, ValueError):
            return ThumbnailResult(None, False)
        return ThumbnailResult(target, True)
