"""tone_curve op：将 0–255 控制点烘成固定 1024 项 float32 LUT。"""
from __future__ import annotations

import numpy as np

from ..base import Domain, Stage
from .._numba import register_jitable


@register_jitable(inline="always")
def _sample_lut(value, lut):
    pos = min(1.0, max(0.0, value)) * 1023.0
    low = int(np.floor(pos))
    high = min(low + 1, 1023)
    fraction = pos - low
    return lut[low] * (1 - fraction) + lut[high] * fraction


@register_jitable(inline="always")
def tone_curve_px(r, g, b, lut):
    return _sample_lut(r, lut), _sample_lut(g, lut), _sample_lut(b, lut)


class ToneCurve:
    name = "tone_curve"
    stage = Stage.FUSED
    domain = Domain.DISPLAY

    def resolve(self, analysis):
        curve = sorted(
            (point["input"], point["output"])
            for point in analysis.get("tone_curve", [])
        )
        if len(curve) < 2:
            return None
        xs = [point[0] for point in curve]
        ys = [point[1] for point in curve]
        if xs[0] > 0:
            xs = [0] + xs
            ys = [ys[0] - xs[1]] + ys
        if xs[-1] < 255:
            ys = ys + [ys[-1] + (255 - xs[-1])]
            xs = xs + [255]
        xs_array = np.asarray(xs, dtype=np.float32) / 255.0
        ys_array = np.clip(np.asarray(ys, dtype=np.float32), 0, 255) / 255.0
        grid = np.linspace(0.0, 1.0, 1024, dtype=np.float32)
        lut = np.interp(grid, xs_array, ys_array).astype(np.float32)
        return (np.ascontiguousarray(lut),)

    def apply_numpy(self, arr, params, aux=None):
        (lut,) = params
        pos = np.clip(arr, 0, 1) * np.float32(1023.0)
        low = np.floor(pos).astype(np.int32)
        high = np.minimum(low + 1, 1023)
        fraction = pos - low
        return (
            lut[low] * (1 - fraction) + lut[high] * fraction
        ).astype(np.float32)

    apply_px = staticmethod(tone_curve_px)
