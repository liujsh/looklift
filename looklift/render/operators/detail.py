"""detail 面板 op：texture 与 clarity 的方向正确近似。"""
from __future__ import annotations

import numpy as np

from .._legacy import _luminance
from .._numba import register_jitable
from ..base import Domain, Stage


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
