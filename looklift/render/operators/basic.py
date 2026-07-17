"""basic 面板 op：曝光、白平衡、对比度、高光阴影与白黑场。

apply_numpy 的数学逐字搬自旧色彩管线，本任务仍全部位于 display 域。
"""
from __future__ import annotations

import numpy as np

from .._legacy import _luminance
from ..base import Domain, Stage


class Exposure:
    name = "exposure"
    stage = Stage.FUSED
    domain = Domain.DISPLAY

    def resolve(self, analysis):
        ev = analysis.get("basic", {}).get("exposure", 0)
        return None if not ev else (float(ev),)

    def apply_numpy(self, arr, params, aux=None):
        (ev,) = params
        return (arr.astype(np.float32) * (2.0 ** ev)).astype(np.float32)


class WhiteBalance:
    name = "white_balance"
    stage = Stage.FUSED
    domain = Domain.DISPLAY

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
