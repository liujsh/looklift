"""effects 面板 op：OUTPUT 阶段 vignette 与 grain。"""
from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from .._legacy import _luminance
from ..base import Domain, Stage


def grain_px(r, g, b, amount, noise):
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    delta = amount / 100.0 * 0.1 * 4.0 * luma * (1.0 - luma) * noise
    return r + delta, g + delta, b + delta


def vignette_px(r, g, b, amount, radius_squared):
    gain = 1.0 + amount / 100.0 * 0.6 * radius_squared
    return r * gain, g * gain, b * gain


class Vignette:
    name = "vignette"
    stage = Stage.OUTPUT
    domain = Domain.DISPLAY

    def resolve(self, analysis):
        amount = analysis.get("effects", {}).get("vignette_amount", 0)
        return None if not amount else (float(amount),)

    def apply_numpy(self, arr, params, aux=None):
        (amount,) = params
        height, width = arr.shape[:2]
        y, x = np.mgrid[0:height, 0:width]
        radius = np.sqrt(
            ((x / width - 0.5) * 2.0) ** 2
            + ((y / height - 0.5) * 2.0) ** 2
        ) / np.sqrt(2.0)
        return (arr * (1.0 + amount / 100.0 * 0.6 * radius**2)[..., None]).astype(
            np.float32
        )

    apply_px = staticmethod(vignette_px)


class Grain:
    name = "grain"
    stage = Stage.OUTPUT
    domain = Domain.DISPLAY

    def resolve(self, analysis):
        amount = analysis.get("effects", {}).get("grain_amount", 0)
        return None if not amount else (float(amount),)

    def apply_numpy(self, arr, params, aux=None):
        if aux is None or aux.noise is None:
            raise ValueError("grain 必须消费 S2 生成的唯一噪声场")
        (amount,) = params
        luma = _luminance(arr)
        weight = 4.0 * luma * (1.0 - luma)
        delta = amount / 100.0 * 0.1 * weight * aux.noise
        return (arr + delta[..., None]).astype(np.float32)

    apply_px = staticmethod(grain_px)


def noise_aux(noise):
    """为唯一 S4 grain 数学构造最小只读辅助视图。"""

    return SimpleNamespace(noise=noise)
