"""渲染引擎包对外入口。

v2.0-A 起 render.py 拆为 render/ 包(operator 化 + 线性光 + numba 融合)。
本 __init__ 冻结对外契约:render / score 签名语义不变;旧内部符号
在迁移期继续兼容；_apply_color_ops 已作为 shim 转入新 pipeline，
供 lut.py 与 test_render.py 现有引用零改动。
"""
from __future__ import annotations

import numpy as np
from PIL import Image

from . import pipeline
from ._legacy import (  # noqa: F401  迁移期兼容 re-export
    _HSL_CENTERS,
    _apply_color_grading,
    _apply_spatial_ops,
    _hsv_to_rgb,
    _luminance,
    _rgb_to_hsv,
    score,
)


def _apply_color_ops(arr: np.ndarray, analysis: dict) -> np.ndarray:
    """迁移期兼容入口，颜色处理统一转入分阶段 NumPy 管线。"""

    return pipeline.render_arr(arr, analysis)


def render(image: Image.Image, analysis: dict) -> Image.Image:
    """按冻结签名渲染图像，空间操作继续复用旧参考实现。"""

    if image.mode != "RGB":
        image = image.convert("RGB")
    arr = np.asarray(image, dtype=np.float32) / 255.0
    arr = pipeline.render_arr(arr, analysis)
    arr = _apply_spatial_ops(arr, analysis)
    return Image.fromarray((arr * 255 + 0.5).astype(np.uint8), "RGB")


__all__ = ["render", "score"]
