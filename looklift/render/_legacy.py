"""本地近似渲染:把 analysis 参数应用到图片上。

定位是「方向正确的近似」,不承诺与 Lightroom 渲染一致(见 v0.3 spec)。
输入假设 sRGB;内部用 float32 0-1 numpy 数组。
_apply_color_ops 只含全局色彩映射(LUT 导出复用);暗角等空间效果在 _apply_spatial_ops。
"""
from __future__ import annotations

import numpy as np
from PIL import Image

_HSL_CENTERS = {  # 8 通道中心色相(度)
    "red": 0, "orange": 30, "yellow": 60, "green": 120,
    "aqua": 180, "blue": 240, "purple": 280, "magenta": 320,
}


def _luminance(arr: np.ndarray) -> np.ndarray:
    return arr[..., 0] * 0.2126 + arr[..., 1] * 0.7152 + arr[..., 2] * 0.0722


def _rgb_to_hsv(arr: np.ndarray) -> np.ndarray:
    """向量化 RGB→HSV。arr: float32 (...,3) 0-1。返回 (...,3):h 度 0-360,s/v 0-1。"""
    arr = arr.astype(np.float32)
    r, g, b = arr[..., 0], arr[..., 1], arr[..., 2]
    maxc = arr.max(axis=-1)
    minc = arr.min(axis=-1)
    delta = maxc - minc

    # 避免除零:delta 为 0 处色相/饱和度按 0 处理
    safe_delta = np.where(delta == 0, 1.0, delta)

    rc = (maxc - r) / safe_delta
    gc = (maxc - g) / safe_delta
    bc = (maxc - b) / safe_delta

    hue = np.select(
        [maxc == r, maxc == g, maxc == b],
        [bc - gc, 2.0 + rc - bc, 4.0 + gc - rc],
        default=0.0,
    )
    hue = (hue * 60.0) % 360.0
    hue = np.where(delta == 0, 0.0, hue)

    safe_maxc = np.where(maxc == 0, 1.0, maxc)
    sat = np.where(maxc == 0, 0.0, delta / safe_maxc)
    val = maxc

    return np.stack([hue, sat, val], axis=-1).astype(np.float32)


def _hsv_to_rgb(arr: np.ndarray) -> np.ndarray:
    """逆变换:(...,3) h 度 0-360,s/v 0-1 → RGB float32 0-1。"""
    arr = arr.astype(np.float32)
    h, s, v = arr[..., 0], arr[..., 1], arr[..., 2]
    h = np.mod(h, 360.0) / 60.0  # 0-6
    i = np.floor(h).astype(np.int64) % 6
    f = h - np.floor(h)

    p = v * (1 - s)
    q = v * (1 - s * f)
    t = v * (1 - s * (1 - f))

    r = np.select(
        [i == 0, i == 1, i == 2, i == 3, i == 4, i == 5],
        [v, q, p, p, t, v],
    )
    g = np.select(
        [i == 0, i == 1, i == 2, i == 3, i == 4, i == 5],
        [t, v, v, q, p, p],
    )
    b = np.select(
        [i == 0, i == 1, i == 2, i == 3, i == 4, i == 5],
        [p, p, t, v, v, q],
    )
    return np.stack([r, g, b], axis=-1).astype(np.float32)


def _apply_color_ops(arr: np.ndarray, analysis: dict) -> np.ndarray:
    b = analysis.get("basic", {})
    arr = arr.astype(np.float32)

    # 1) 曝光:2^ev 增益
    ev = b.get("exposure", 0)
    if ev:
        arr = arr * (2.0 ** ev)

    # 2) 白平衡:温/色调通道增益(±100 → ±20% 通道差)
    t, tint = b.get("temperature_shift", 0), b.get("tint_shift", 0)
    if t:
        arr[..., 0] *= 1 + 0.2 * t / 100
        arr[..., 2] *= 1 - 0.2 * t / 100
    if tint:
        arr[..., 1] *= 1 - 0.15 * tint / 100  # 品红=压绿

    # 3) 对比度:围绕 0.5 的线性扩张(±100 → ±60%)
    c = b.get("contrast", 0)
    if c:
        arr = 0.5 + (arr - 0.5) * (1 + 0.6 * c / 100)

    # 4) 高光/阴影:亮度蒙版加权提亮/压暗
    arr = np.clip(arr, 0, 1)
    luma = _luminance(arr)[..., None]
    hi, sh = b.get("highlights", 0), b.get("shadows", 0)
    if hi:
        arr = arr + (hi / 100) * 0.25 * (luma ** 2)  # 亮区权重 luma²
    if sh:
        arr = arr + (sh / 100) * 0.25 * ((1 - luma) ** 2)

    # 5) 白/黑场:端点缩放
    wh, bl = b.get("whites", 0), b.get("blacks", 0)
    if wh:
        arr = arr * (1 + 0.15 * wh / 100)
    if bl:
        arr = arr + 0.15 * bl / 100 * (1 - np.clip(arr, 0, 1)) ** 4  # 只影响近黑

    arr = np.clip(arr, 0, 1)

    # 6) 色调曲线:0-255 控制点 → np.interp LUT
    curve = sorted(
        ((p["input"], p["output"]) for p in analysis.get("tone_curve", [])),
    )
    if len(curve) >= 2:
        xs = [p[0] for p in curve]
        ys = [p[1] for p in curve]
        # schema 只要求控制点"接近"0/255 端点,不保证严格达到;np.interp 对
        # 超出定义域的输入会直接夹到边界 y 值,若端点不是 (0,0)/(255,255)
        # 就会把定义域外的像素错误地拉平。曲线域外按斜率 1 外推,保证恒等
        # 曲线严格恒等:在两端各补一个虚拟端点,把定义域强制补满到 0-255,
        # 超界部分按 45° 斜率延伸而不是被夹平。
        if xs[0] > 0:
            xs = [0] + xs
            ys = [ys[0] - xs[1]] + ys
        if xs[-1] < 255:
            ys = ys + [ys[-1] + (255 - xs[-1])]
            xs = xs + [255]
        xs = np.array(xs, dtype=np.float64) / 255.0
        ys = np.clip(np.array(ys, dtype=np.float64), 0, 255) / 255.0
        arr = np.interp(arr, xs, ys).astype(np.float32)

    # 7) HSL 定向 + 8) 饱和度/自然饱和度:HSV 域一次完成
    hsv = _rgb_to_hsv(arr)
    for entry in analysis.get("hsl", []):
        center = _HSL_CENTERS.get(entry.get("color", ""), None)
        if center is None:
            continue
        dist = np.abs((hsv[..., 0] - center + 180) % 360 - 180)
        mask = np.clip(1 - dist / 45, 0, 1)  # 中心±45° 三角权重
        hsv[..., 0] = (hsv[..., 0] + mask * entry.get("hue", 0) * 0.3) % 360
        hsv[..., 1] *= 1 + mask * entry.get("saturation", 0) / 100 * 0.5
        hsv[..., 2] *= 1 + mask * entry.get("luminance", 0) / 100 * 0.3

    sat, vib = b.get("saturation", 0), b.get("vibrance", 0)
    if sat:
        hsv[..., 1] *= 1 + sat / 100
    if vib:  # 自然饱和度:低饱和像素受益更多
        hsv[..., 1] += (vib / 100) * 0.5 * hsv[..., 1] * (1 - hsv[..., 1])
    hsv[..., 1] = np.clip(hsv[..., 1], 0, 1)
    arr = _hsv_to_rgb(hsv)

    # 9) 颜色分级:亮度加权叠色(shadows/midtones/highlights/global_)
    arr = _apply_color_grading(arr, analysis.get("color_grading", {}))
    return np.clip(arr, 0, 1).astype(np.float32)


def _apply_color_grading(arr, cg):
    luma = _luminance(arr)[..., None]
    weights = {
        "shadows": (1 - luma) ** 2, "midtones": 4 * luma * (1 - luma),
        "highlights": luma ** 2, "global_": np.ones_like(luma),
    }
    for zone, w in weights.items():
        z = cg.get(zone, {})
        s = z.get("saturation", 0)
        lum = z.get("luminance", 0)
        if not s and not lum:
            continue  # 饱和度与明亮度都为 0 才整体跳过,二者应可独立生效
        if s:
            hue = np.deg2rad(z.get("hue", 0))
            tint = (np.array(
                [np.cos(hue), np.cos(hue - 2.0944), np.cos(hue - 4.1888)],
                dtype=np.float32,
            ) * 0.5 + 0.5)
            arr = arr + w * (s / 100) * 0.3 * (tint - arr)
        if lum:
            arr = arr + w * lum / 100 * 0.2
    return arr


def _apply_spatial_ops(arr: np.ndarray, analysis: dict) -> np.ndarray:
    v = analysis.get("effects", {}).get("vignette_amount", 0)
    if v:
        h, w = arr.shape[:2]
        y, x = np.mgrid[0:h, 0:w]
        r = np.sqrt(((x / w - 0.5) * 2) ** 2 + ((y / h - 0.5) * 2) ** 2) / np.sqrt(2)
        arr = arr * (1 + (v / 100) * 0.6 * (r ** 2))[..., None]
    return np.clip(arr, 0, 1)


def render(image: Image.Image, analysis: dict) -> Image.Image:
    if image.mode != "RGB":
        image = image.convert("RGB")
    arr = np.asarray(image, dtype=np.float32) / 255.0
    arr = _apply_color_ops(arr, analysis)
    arr = _apply_spatial_ops(arr, analysis)
    return Image.fromarray((arr * 255 + 0.5).astype(np.uint8), "RGB")


def _ab_stats(arr):
    """近似 Lab 的 a/b 通道均值与标准差(色彩倾向指纹)。"""
    a = arr[..., 0] - arr[..., 1]          # 红绿轴
    b_ = arr[..., 1] - arr[..., 2]         # 黄蓝轴
    return np.array([a.mean(), b_.mean(), a.std(), b_.std()])


def score(rendered: Image.Image, target: Image.Image) -> float:
    """还原度 0-100。只用于同一目标的迭代趋势判断,不做跨风格比较。"""
    def prep(im):
        im = im.convert("RGB")
        im.thumbnail((256, 256))
        return np.asarray(im, dtype=np.float32) / 255.0
    r, t = prep(rendered), prep(target)

    hr, _ = np.histogram(_luminance(r), bins=64, range=(0, 1), density=True)
    ht, _ = np.histogram(_luminance(t), bins=64, range=(0, 1), density=True)
    denom = np.linalg.norm(hr) * np.linalg.norm(ht)
    hist_sim = float(hr @ ht / denom) if denom else 0.0   # 余弦相似度 0-1

    d = np.abs(_ab_stats(r) - _ab_stats(t))
    color_sim = float(np.clip(1 - d.mean() / 0.15, 0, 1))

    return round(100 * (0.6 * hist_sim + 0.4 * color_sim), 1)
