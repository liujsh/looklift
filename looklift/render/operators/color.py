"""color 面板 op：HSL、饱和度与颜色分级。

数学逐字搬自旧色彩管线；HSL 八色键唯一来自 analyzer._COLOR_KEYS。
"""
from __future__ import annotations

import numpy as np

from ...analyzer import _COLOR_KEYS
from .._legacy import _hsv_to_rgb, _luminance, _rgb_to_hsv
from ..base import Domain, Stage

_CENTER_VALUES = (0, 30, 60, 120, 180, 240, 280, 320)
_HSL_CENTERS = dict(zip(_COLOR_KEYS, _CENTER_VALUES, strict=True))


class Hsl:
    name = "hsl"
    stage = Stage.FUSED
    domain = Domain.DISPLAY

    def resolve(self, analysis):
        by_color = {entry.get("color"): entry for entry in analysis.get("hsl", [])}
        values = np.zeros((len(_COLOR_KEYS), 3), dtype=np.float32)
        for index, color in enumerate(_COLOR_KEYS):
            entry = by_color.get(color, {})
            values[index] = (
                entry.get("hue", 0),
                entry.get("saturation", 0),
                entry.get("luminance", 0),
            )
        if not np.any(values):
            return None
        return (np.ascontiguousarray(values.reshape(-1)),)

    def apply_numpy(self, arr, params, aux=None):
        values = params[0].reshape(len(_COLOR_KEYS), 3)
        hsv = _rgb_to_hsv(arr)
        for center, (hue, saturation, luminance) in zip(
            _CENTER_VALUES, values, strict=True
        ):
            dist = np.abs((hsv[..., 0] - center + 180) % 360 - 180)
            mask = np.clip(1 - dist / 45, 0, 1)
            hsv[..., 0] = (hsv[..., 0] + mask * hue * 0.3) % 360
            hsv[..., 1] *= 1 + mask * saturation / 100 * 0.5
            hsv[..., 2] *= 1 + mask * luminance / 100 * 0.3
        return _hsv_to_rgb(hsv)


class Saturation:
    name = "saturation"
    stage = Stage.FUSED
    domain = Domain.DISPLAY

    def resolve(self, analysis):
        basic = analysis.get("basic", {})
        saturation = basic.get("saturation", 0)
        vibrance = basic.get("vibrance", 0)
        return None if (not saturation and not vibrance) else (
            float(saturation),
            float(vibrance),
        )

    def apply_numpy(self, arr, params, aux=None):
        saturation, vibrance = params
        hsv = _rgb_to_hsv(arr)
        if saturation:
            hsv[..., 1] *= 1 + saturation / 100
        if vibrance:
            hsv[..., 1] += (vibrance / 100) * 0.5 * hsv[..., 1] * (1 - hsv[..., 1])
        hsv[..., 1] = np.clip(hsv[..., 1], 0, 1)
        return _hsv_to_rgb(hsv)


class ColorGrading:
    name = "color_grading"
    stage = Stage.FUSED
    domain = Domain.DISPLAY

    def resolve(self, analysis):
        color_grading = analysis.get("color_grading", {})
        zones = ("shadows", "midtones", "highlights", "global_")
        values = np.asarray(
            [
                (
                    color_grading.get(zone, {}).get("hue", 0),
                    color_grading.get(zone, {}).get("saturation", 0),
                    color_grading.get(zone, {}).get("luminance", 0),
                )
                for zone in zones
            ],
            dtype=np.float32,
        )
        if not np.any(values[:, 1:]):
            return None
        return (np.ascontiguousarray(values.reshape(-1)),)

    def apply_numpy(self, arr, params, aux=None):
        values = params[0].reshape(4, 3)
        luma = _luminance(arr)[..., None]
        weights = {
            "shadows": (1 - luma) ** 2,
            "midtones": 4 * luma * (1 - luma),
            "highlights": luma ** 2,
            "global_": np.ones_like(luma),
        }
        for (_zone, weight), (hue_degrees, saturation, luminance) in zip(
            weights.items(), values, strict=True
        ):
            if not saturation and not luminance:
                continue
            if saturation:
                hue = np.deg2rad(hue_degrees)
                tint = (
                    np.asarray(
                        [np.cos(hue), np.cos(hue - 2.0944), np.cos(hue - 4.1888)],
                        dtype=np.float32,
                    )
                    * 0.5
                    + 0.5
                )
                arr = arr + weight * (saturation / 100) * 0.3 * (tint - arr)
            if luminance:
                arr = arr + weight * luminance / 100 * 0.2
        return arr.astype(np.float32)
