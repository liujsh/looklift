"""color 面板 op：HSL、饱和度与颜色分级。

数学逐字搬自旧色彩管线；HSL 八色键唯一来自 analyzer._COLOR_KEYS。
"""
from __future__ import annotations

import math

import numpy as np

from ...analyzer import _COLOR_KEYS
from .._legacy import _hsv_to_rgb, _luminance, _rgb_to_hsv
from ..base import Domain, Stage
from .._numba import register_jitable

_CENTER_VALUES = (0, 30, 60, 120, 180, 240, 280, 320)
_HSL_CENTERS = dict(zip(_COLOR_KEYS, _CENTER_VALUES, strict=True))


@register_jitable(inline="always")
def _rgb_to_hsv_px(r, g, b):
    maxc = max(r, g, b)
    minc = min(r, g, b)
    delta = maxc - minc
    if delta == 0.0:
        hue = 0.0
    elif maxc == r:
        hue = ((g - b) / delta * 60.0) % 360.0
    elif maxc == g:
        hue = (2.0 + (b - r) / delta) * 60.0
    else:
        hue = (4.0 + (r - g) / delta) * 60.0
    saturation = 0.0 if maxc == 0.0 else delta / maxc
    return hue, saturation, maxc


@register_jitable(inline="always")
def _hsv_to_rgb_px(hue, saturation, value):
    scaled = (hue % 360.0) / 60.0
    sector = int(math.floor(scaled)) % 6
    fraction = scaled - math.floor(scaled)
    p = value * (1.0 - saturation)
    q = value * (1.0 - saturation * fraction)
    t = value * (1.0 - saturation * (1.0 - fraction))
    if sector == 0:
        return value, t, p
    if sector == 1:
        return q, value, p
    if sector == 2:
        return p, value, t
    if sector == 3:
        return p, q, value
    if sector == 4:
        return t, p, value
    return value, p, q


@register_jitable(inline="always")
def hsl_px(r, g, b, values):
    hue, saturation, value = _rgb_to_hsv_px(r, g, b)
    for index in range(8):
        offset = index * 3
        if (
            values[offset] == 0.0
            and values[offset + 1] == 0.0
            and values[offset + 2] == 0.0
        ):
            continue
        center = _CENTER_VALUES[index]
        distance = abs((hue - center + 180.0) % 360.0 - 180.0)
        mask = min(1.0, max(0.0, 1.0 - distance / 45.0))
        hue = (hue + mask * values[offset] * 0.3) % 360.0
        saturation *= 1.0 + mask * values[offset + 1] / 100.0 * 0.5
        value *= 1.0 + mask * values[offset + 2] / 100.0 * 0.3
    return _hsv_to_rgb_px(hue, saturation, value)


@register_jitable(inline="always")
def saturation_px(r, g, b, saturation_shift, vibrance):
    hue, saturation, value = _rgb_to_hsv_px(r, g, b)
    saturation *= 1.0 + saturation_shift / 100.0
    saturation += vibrance / 100.0 * 0.5 * saturation * (1.0 - saturation)
    saturation = min(1.0, max(0.0, saturation))
    return _hsv_to_rgb_px(hue, saturation, value)


@register_jitable(inline="always")
def color_grading_with_tints_px(r, g, b, values, tints):
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    weights = (
        (1.0 - luma) ** 2,
        4.0 * luma * (1.0 - luma),
        luma**2,
        1.0,
    )
    for index in range(4):
        offset = index * 3
        saturation = values[offset + 1]
        luminance = values[offset + 2]
        weight = weights[index]
        if saturation != 0.0:
            amount = weight * saturation / 100.0 * 0.3
            r += amount * (tints[offset] - r)
            g += amount * (tints[offset + 1] - g)
            b += amount * (tints[offset + 2] - b)
        if luminance != 0.0:
            amount = weight * luminance / 100.0 * 0.2
            r += amount
            g += amount
            b += amount
    return r, g, b


@register_jitable(inline="always")
def color_grading_px(r, g, b, values):
    """operator 级逐像素入口；融合内核会把固定 hue tint 提前烘好。"""

    tints = np.zeros(12, dtype=np.float32)
    for index in range(4):
        offset = index * 3
        angle = values[offset] * math.pi / 180.0
        tints[offset] = math.cos(angle) * 0.5 + 0.5
        tints[offset + 1] = math.cos(angle - 2.0944) * 0.5 + 0.5
        tints[offset + 2] = math.cos(angle - 4.1888) * 0.5 + 0.5
    return color_grading_with_tints_px(r, g, b, values, tints)


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

    apply_px = staticmethod(hsl_px)


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

    apply_px = staticmethod(saturation_px)


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

    apply_px = staticmethod(color_grading_px)
