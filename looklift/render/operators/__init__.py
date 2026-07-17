"""Operator 注册表，顺序与 Stage/OP_BITS 一致。"""
from __future__ import annotations

from .basic import Contrast, Exposure, HighlightsShadows, WhiteBalance, WhitesBlacks
from .color import ColorGrading, Hsl, Saturation
from .detail import Clarity, Dehaze, Texture
from .tone import ToneCurve

REGISTRY = [
    Exposure(),
    WhiteBalance(),
    Contrast(),
    HighlightsShadows(),
    WhitesBlacks(),
    ToneCurve(),
    Hsl(),
    Saturation(),
    ColorGrading(),
    Texture(),
    Clarity(),
    Dehaze(),
]
