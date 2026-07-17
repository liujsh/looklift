"""basic 面板 op：曝光、白平衡、对比度、高光阴影与白黑场。

apply_numpy 的数学逐字搬自旧色彩管线；曝光与白平衡位于线性光域。
"""
from __future__ import annotations

import numpy as np

from .._legacy import _luminance
from ..base import Domain, Stage
from .._numba import register_jitable


@register_jitable(inline="always")
def exposure_px(r, g, b, ev):
    gain = 2.0**ev
    return r * gain, g * gain, b * gain


@register_jitable(inline="always")
def white_balance_px(r, g, b, temperature, tint):
    return (
        r * (1.0 + 0.2 * temperature / 100.0),
        g * (1.0 - 0.15 * tint / 100.0),
        b * (1.0 - 0.2 * temperature / 100.0),
    )


@register_jitable(inline="always")
def contrast_px(r, g, b, contrast):
    gain = 1.0 + 0.6 * contrast / 100.0
    return (
        0.5 + (r - 0.5) * gain,
        0.5 + (g - 0.5) * gain,
        0.5 + (b - 0.5) * gain,
    )


@register_jitable(inline="always")
def highlights_shadows_px(r, g, b, highlights, shadows):
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    delta = (
        highlights / 100.0 * 0.25 * luma**2
        + shadows / 100.0 * 0.25 * (1.0 - luma) ** 2
    )
    return r + delta, g + delta, b + delta


@register_jitable(inline="always")
def _clip01(value):
    return min(1.0, max(0.0, value))


@register_jitable(inline="always")
def whites_blacks_px(r, g, b, whites, blacks):
    gain = 1.0 + 0.15 * whites / 100.0
    black_gain = 0.15 * blacks / 100.0
    r *= gain
    g *= gain
    b *= gain
    return (
        r + black_gain * (1.0 - _clip01(r)) ** 4,
        g + black_gain * (1.0 - _clip01(g)) ** 4,
        b + black_gain * (1.0 - _clip01(b)) ** 4,
    )


class Exposure:
    name = "exposure"
    stage = Stage.FUSED
    domain = Domain.LINEAR

    def resolve(self, analysis):
        ev = analysis.get("basic", {}).get("exposure", 0)
        return None if not ev else (float(ev),)

    def apply_numpy(self, arr, params, aux=None):
        (ev,) = params
        return (arr.astype(np.float32) * (2.0 ** ev)).astype(np.float32)

    apply_px = staticmethod(exposure_px)


class WhiteBalance:
    name = "white_balance"
    stage = Stage.FUSED
    domain = Domain.LINEAR

    def resolve(self, analysis):
        basic = analysis.get("basic", {})
        temperature = basic.get("temperature_shift", 0)
        tint = basic.get("tint_shift", 0)
        return None if (not temperature and not tint) else (
            float(temperature),
            float(tint),
        )

    def apply_numpy(self, arr, params, aux=None):
        temperature, tint = params
        arr = arr.astype(np.float32).copy()
        if temperature:
            arr[..., 0] *= 1 + 0.2 * temperature / 100
            arr[..., 2] *= 1 - 0.2 * temperature / 100
        if tint:
            arr[..., 1] *= 1 - 0.15 * tint / 100  # 品红偏移通过压低绿通道实现
        return arr

    apply_px = staticmethod(white_balance_px)


class Contrast:
    name = "contrast"
    stage = Stage.FUSED
    domain = Domain.DISPLAY

    def resolve(self, analysis):
        contrast = analysis.get("basic", {}).get("contrast", 0)
        return None if not contrast else (float(contrast),)

    def apply_numpy(self, arr, params, aux=None):
        (contrast,) = params
        return (
            0.5 + (arr - 0.5) * (1 + 0.6 * contrast / 100)
        ).astype(np.float32)

    apply_px = staticmethod(contrast_px)


class HighlightsShadows:
    name = "highlights_shadows"
    stage = Stage.FUSED
    domain = Domain.DISPLAY

    def resolve(self, analysis):
        basic = analysis.get("basic", {})
        highlights = basic.get("highlights", 0)
        shadows = basic.get("shadows", 0)
        return None if (not highlights and not shadows) else (
            float(highlights),
            float(shadows),
        )

    def apply_numpy(self, arr, params, aux=None):
        highlights, shadows = params
        arr = arr.astype(np.float32)
        luma = _luminance(arr)[..., None]
        if highlights:
            arr = arr + (highlights / 100) * 0.25 * (luma ** 2)
        if shadows:
            arr = arr + (shadows / 100) * 0.25 * ((1 - luma) ** 2)
        return arr.astype(np.float32)

    apply_px = staticmethod(highlights_shadows_px)


class WhitesBlacks:
    name = "whites_blacks"
    stage = Stage.FUSED
    domain = Domain.DISPLAY

    def resolve(self, analysis):
        basic = analysis.get("basic", {})
        whites = basic.get("whites", 0)
        blacks = basic.get("blacks", 0)
        return None if (not whites and not blacks) else (
            float(whites),
            float(blacks),
        )

    def apply_numpy(self, arr, params, aux=None):
        whites, blacks = params
        arr = arr.astype(np.float32)
        if whites:
            arr = arr * (1 + 0.15 * whites / 100)
        if blacks:
            arr = arr + 0.15 * blacks / 100 * (1 - np.clip(arr, 0, 1)) ** 4
        return arr.astype(np.float32)

    apply_px = staticmethod(whites_blacks_px)
