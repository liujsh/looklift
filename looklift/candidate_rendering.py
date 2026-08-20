"""候选 JPEG 渲染和确定性基础指标。"""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image

from .agent_tool_contract import CandidateMetrics
from .ai_proxy import prepare_ai_proxy


class ProxyCandidateRenderer:
    """复用现有 2048px 无 EXIF 代理链渲染候选。"""

    def render(self, image_path: Path, analysis: dict) -> bytes:
        with prepare_ai_proxy(
            image_path,
            analysis=analysis,
            factor=1,
            include_metadata=False,
        ) as proxy:
            return proxy.path.read_bytes()


def candidate_metrics(jpeg: bytes) -> CandidateMetrics:
    """从实际返回模型的 JPEG 计算亮度和近黑/近白裁切比例。"""
    with Image.open(io.BytesIO(jpeg)) as opened:
        if opened.format != "JPEG":
            raise ValueError("候选预览必须是 JPEG")
        rgb = np.asarray(opened.convert("RGB"), dtype=np.float32) / 255.0
    luminance = (
        rgb[..., 0] * np.float32(0.2126)
        + rgb[..., 1] * np.float32(0.7152)
        + rgb[..., 2] * np.float32(0.0722)
    )
    return CandidateMetrics(
        mean_luminance=float(luminance.mean()),
        shadow_clip_ratio=float((luminance <= (2 / 255)).mean()),
        highlight_clip_ratio=float((luminance >= (253 / 255)).mean()),
    )
