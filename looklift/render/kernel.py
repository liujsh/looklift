"""Numba 单遍 pointwise 融合内核与固定渲染参数 ABI。"""
from __future__ import annotations

from typing import NamedTuple

import numpy as np

from ._numba import HAS_NUMBA, NumbaError, njit, prange
from .base import OP_BITS
from .operators.basic import (
    contrast_px,
    exposure_px,
    highlights_shadows_px,
    white_balance_px,
    whites_blacks_px,
)
from .operators.color import color_grading_px, hsl_px, saturation_px
from .operators.tone import tone_curve_px


RENDER_PARAM_LAYOUT = (
    ("enable", "int64", ()),
    ("exposure", "float32", ()),
    ("white_balance", "float32", (2,)),
    ("contrast", "float32", ()),
    ("highlights_shadows", "float32", (2,)),
    ("whites_blacks", "float32", (2,)),
    ("tone_curve_lut", "float32", (1024,)),
    ("hsl", "float32", (24,)),
    ("saturation", "float32", (2,)),
    ("color_grading", "float32", (12,)),
)


class RenderParams(NamedTuple):
    """送入 nopython 内核的唯一固定参数结构。"""

    enable: int
    exposure: np.float32
    white_balance: np.ndarray
    contrast: np.float32
    highlights_shadows: np.ndarray
    whites_blacks: np.ndarray
    tone_curve_lut: np.ndarray
    hsl: np.ndarray
    saturation: np.ndarray
    color_grading: np.ndarray


_EXPOSURE = OP_BITS["exposure"]
_WHITE_BALANCE = OP_BITS["white_balance"]
_CONTRAST = OP_BITS["contrast"]
_HIGHLIGHTS_SHADOWS = OP_BITS["highlights_shadows"]
_WHITES_BLACKS = OP_BITS["whites_blacks"]
_TONE_CURVE = OP_BITS["tone_curve"]
_HSL = OP_BITS["hsl"]
_SATURATION = OP_BITS["saturation"]
_COLOR_GRADING = OP_BITS["color_grading"]


@njit(inline="always")
def _clip01(value):
    return min(1.0, max(0.0, value))


@njit(inline="always")
def _srgb_to_linear(value):
    if value <= 0.04045:
        return value / 12.92
    return ((value + 0.055) / 1.055) ** 2.4


@njit(inline="always")
def _linear_to_srgb(value):
    if value <= 0.0031308:
        return 12.92 * value
    return 1.055 * value ** (1.0 / 2.4) - 0.055


@njit(cache=True)
def probe_render_params(params):
    """触发并验证固定 record 可进入 nopython。"""

    return params.enable


@njit(parallel=True, fastmath=True, cache=True)
def fused(arr_srgb, params, aux=None):
    """单遍执行 linear→OETF→display pointwise operator。"""

    height, width, _channels = arr_srgb.shape
    output = np.empty_like(arr_srgb)
    for y in prange(height):
        for x in range(width):
            r = _srgb_to_linear(arr_srgb[y, x, 0])
            g = _srgb_to_linear(arr_srgb[y, x, 1])
            b = _srgb_to_linear(arr_srgb[y, x, 2])

            if params.enable & _EXPOSURE:
                r, g, b = exposure_px(r, g, b, params.exposure)
            if params.enable & _WHITE_BALANCE:
                r, g, b = white_balance_px(
                    r,
                    g,
                    b,
                    params.white_balance[0],
                    params.white_balance[1],
                )

            r = _clip01(_linear_to_srgb(r))
            g = _clip01(_linear_to_srgb(g))
            b = _clip01(_linear_to_srgb(b))

            if params.enable & _CONTRAST:
                r, g, b = contrast_px(r, g, b, params.contrast)
            r, g, b = _clip01(r), _clip01(g), _clip01(b)

            if params.enable & _HIGHLIGHTS_SHADOWS:
                r, g, b = highlights_shadows_px(
                    r,
                    g,
                    b,
                    params.highlights_shadows[0],
                    params.highlights_shadows[1],
                )
            if params.enable & _WHITES_BLACKS:
                r, g, b = whites_blacks_px(
                    r,
                    g,
                    b,
                    params.whites_blacks[0],
                    params.whites_blacks[1],
                )
            r, g, b = _clip01(r), _clip01(g), _clip01(b)

            if params.enable & _TONE_CURVE:
                r, g, b = tone_curve_px(r, g, b, params.tone_curve_lut)
            if params.enable & _HSL:
                r, g, b = hsl_px(r, g, b, params.hsl)
            if params.enable & (_HSL | _SATURATION):
                r, g, b = saturation_px(
                    r,
                    g,
                    b,
                    params.saturation[0],
                    params.saturation[1],
                )
            if params.enable & _COLOR_GRADING:
                r, g, b = color_grading_px(r, g, b, params.color_grading)

            output[y, x, 0] = _clip01(r)
            output[y, x, 1] = _clip01(g)
            output[y, x, 2] = _clip01(b)
    return output
