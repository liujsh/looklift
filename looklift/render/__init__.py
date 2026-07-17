"""渲染引擎包对外入口。

v2.0-A 起 render.py 拆为 render/ 包(operator 化 + 线性光 + numba 融合)。
本 __init__ 冻结对外契约:render / score 签名语义不变;旧内部符号
(_apply_color_ops 等)在迁移期从 _legacy re-export,供 lut.py 与
test_render.py 现有引用零改动。迁移完成后逐步收敛到新 pipeline。
"""
from __future__ import annotations

from ._legacy import (  # noqa: F401  迁移期兼容 re-export
    _HSL_CENTERS,
    _apply_color_grading,
    _apply_color_ops,
    _apply_spatial_ops,
    _hsv_to_rgb,
    _luminance,
    _rgb_to_hsv,
    render,
    score,
)

__all__ = ["render", "score"]
