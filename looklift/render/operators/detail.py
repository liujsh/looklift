"""detail 面板 op：texture 与 clarity 的方向正确近似。"""
from __future__ import annotations

import numpy as np

from .._legacy import _hsv_to_rgb, _luminance, _rgb_to_hsv
from .._numba import register_jitable
from ..base import Domain, Stage
from .color import _hsv_to_rgb_px, _rgb_to_hsv_px


@register_jitable(inline="always")
def texture_px(r, g, b, amount, blur_mid):
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    delta = amount / 100.0 * (luma - blur_mid)
    return r + delta, g + delta, b + delta


@register_jitable(inline="always")
def clarity_px(r, g, b, amount, blur_large):
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    mask = 4.0 * luma * (1.0 - luma)
    gain = amount / 100.0 * mask
    return (
        r + gain * (r - blur_large),
        g + gain * (g - blur_large),
        b + gain * (b - blur_large),
    )


@register_jitable(inline="always")
def dehaze_px(r, g, b, amount, blur_mid):
    strength = amount / 100.0
    local_gain = strength * 0.5
    r += local_gain * (r - blur_mid)
    g += local_gain * (g - blur_mid)
    b += local_gain * (b - blur_mid)
    hue, saturation, value = _rgb_to_hsv_px(r, g, b)
    saturation = min(1.0, max(0.0, saturation * (1.0 + strength * 0.3)))
    r, g, b = _hsv_to_rgb_px(hue, saturation, value)
    black_gain = strength * 0.05
    return (
        r - black_gain * (1.0 - r),
        g - black_gain * (1.0 - g),
        b - black_gain * (1.0 - b),
    )


class Texture:
    name = "texture"
    stage = Stage.FUSED
    domain = Domain.DISPLAY

    def resolve(self, analysis):
        amount = analysis.get("basic", {}).get("texture", 0)
        return None if not amount else (float(amount),)

    def apply_numpy(self, arr, params, aux=None):
        (amount,) = params
        luma = _luminance(arr)
        delta = amount / 100.0 * (luma - aux.blur_mid)
        return (arr + delta[..., None]).astype(np.float32)

    apply_px = staticmethod(texture_px)


class Clarity:
    name = "clarity"
    stage = Stage.FUSED
    domain = Domain.DISPLAY

    def resolve(self, analysis):
        amount = analysis.get("basic", {}).get("clarity", 0)
        return None if not amount else (float(amount),)

    def apply_numpy(self, arr, params, aux=None):
        (amount,) = params
        luma = _luminance(arr)
        mask = 4.0 * luma * (1.0 - luma)
        gain = amount / 100.0 * mask
        return (
            arr + gain[..., None] * (arr - aux.blur_large[..., None])
        ).astype(np.float32)

    apply_px = staticmethod(clarity_px)


class Dehaze:
    """局部对比 + 饱和度近似；明确不使用暗通道先验。"""

    name = "dehaze"
    stage = Stage.FUSED
    domain = Domain.DISPLAY

    def resolve(self, analysis):
        amount = analysis.get("basic", {}).get("dehaze", 0)
        return None if not amount else (float(amount),)

    def apply_numpy(self, arr, params, aux=None):
        (amount,) = params
        strength = amount / 100.0
        arr = arr + strength * 0.5 * (arr - aux.blur_mid[..., None])
        hsv = _rgb_to_hsv(arr)
        hsv[..., 1] = np.clip(hsv[..., 1] * (1.0 + strength * 0.3), 0, 1)
        arr = _hsv_to_rgb(hsv)
        arr = arr - strength * 0.05 * (1.0 - arr)
        return arr.astype(np.float32)

    apply_px = staticmethod(dehaze_px)
