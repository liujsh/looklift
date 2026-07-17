"""分阶段渲染编排；提供线性光与 display 域 NumPy 参考串联。"""

from __future__ import annotations

from typing import NamedTuple

import numpy as np
from PIL import Image

from . import color_space as cs, kernel
from .base import ResolvedParams
from .operators import REGISTRY

_PROXY_LONG_EDGE = 2048


class AuxBuffers(NamedTuple):
    """S2 预处理结果；可跨 pointwise 滑杆变化复用。"""

    blur_mid: np.ndarray
    blur_large: np.ndarray
    noise: np.ndarray


def resolve_params(analysis: dict) -> ResolvedParams:
    """遍历注册表一次解析参数，生成共用的扁平暂存。"""
    return ResolvedParams.pack(
        {operator.name: operator.resolve(analysis) for operator in REGISTRY}
    )


def marshal_render_params(resolved: ResolvedParams) -> kernel.RenderParams:
    """机械复制扁平暂存到固定 numba record；禁用字段填同型零值。"""

    def scalar(name: str) -> np.float32:
        values = resolved.get(name)
        return np.float32(0.0 if values is None else values[0])

    def vector(name: str, size: int, packed: bool = False) -> np.ndarray:
        values = resolved.get(name)
        if values is None:
            return np.zeros(size, dtype=np.float32)
        source = values[0] if packed else values
        return np.ascontiguousarray(np.asarray(source, dtype=np.float32)).copy()

    return kernel.RenderParams(
        np.int64(resolved.enable),
        scalar("exposure"),
        vector("white_balance", 2),
        scalar("contrast"),
        vector("highlights_shadows", 2),
        vector("whites_blacks", 2),
        vector("tone_curve", 1024, packed=True),
        vector("hsl", 24, packed=True),
        vector("saturation", 2),
        vector("color_grading", 12, packed=True),
    )


def apply_color_ops_numpy(arr: np.ndarray, analysis: dict) -> np.ndarray:
    """display 域 operator 串联参考实现，按旧管线顺序执行。"""
    arr = arr.astype(np.float32)
    operators = {operator.name: operator for operator in REGISTRY}
    resolved = resolve_params(analysis)

    for name in ("exposure", "white_balance", "contrast"):
        params = resolved.get(name)
        if params is not None:
            arr = operators[name].apply_numpy(arr, params)

    arr = np.clip(arr, 0, 1)
    for name in ("highlights_shadows", "whites_blacks"):
        params = resolved.get(name)
        if params is not None:
            arr = operators[name].apply_numpy(arr, params)
    arr = np.clip(arr, 0, 1)

    hsl_applied = False
    saturation_applied = False
    for name in ("tone_curve", "hsl", "saturation", "color_grading"):
        params = resolved.get(name)
        if params is not None:
            arr = operators[name].apply_numpy(arr, params)
            if name == "hsl":
                hsl_applied = True
            elif name == "saturation":
                saturation_applied = True
        if name == "saturation" and hsl_applied and not saturation_applied:
            arr = operators[name].apply_numpy(arr, (0.0, 0.0))
            saturation_applied = True

    return np.clip(arr, 0, 1).astype(np.float32)


def render_arr(arr_srgb: np.ndarray, analysis: dict) -> np.ndarray:
    """先在线性光执行曝光/白平衡，再在 display 域执行其余颜色操作。

    单管线只在两段边界切换一次光域；线性段不裁剪，中间值允许超过 1。
    """
    arr = cs.srgb_to_linear(arr_srgb.astype(np.float32))
    operators = {operator.name: operator for operator in REGISTRY}
    resolved = resolve_params(analysis)

    for name in ("exposure", "white_balance"):
        params = resolved.get(name)
        if params is not None:
            arr = operators[name].apply_numpy(arr, params)

    arr = np.clip(cs.linear_to_srgb(arr), 0, 1)

    params = resolved.get("contrast")
    if params is not None:
        arr = operators["contrast"].apply_numpy(arr, params)
    arr = np.clip(arr, 0, 1)

    for name in ("highlights_shadows", "whites_blacks"):
        params = resolved.get(name)
        if params is not None:
            arr = operators[name].apply_numpy(arr, params)
    arr = np.clip(arr, 0, 1)

    hsl_applied = False
    saturation_applied = False
    for name in ("tone_curve", "hsl", "saturation", "color_grading"):
        params = resolved.get(name)
        if params is not None:
            arr = operators[name].apply_numpy(arr, params)
            if name == "hsl":
                hsl_applied = True
            elif name == "saturation":
                saturation_applied = True
        if name == "saturation" and hsl_applied and not saturation_applied:
            arr = operators[name].apply_numpy(arr, (0.0, 0.0))
            saturation_applied = True

    return np.clip(arr, 0, 1).astype(np.float32)


def render_fused(arr_srgb: np.ndarray, analysis: dict, aux=None) -> np.ndarray:
    """生产 pointwise 路径；numba 缺失/JIT 不可用时回退纯 NumPy。"""

    if not kernel.HAS_NUMBA:
        return render_arr(arr_srgb, analysis)
    resolved = resolve_params(analysis)
    params = marshal_render_params(resolved)
    try:
        return kernel.fused(arr_srgb.astype(np.float32), params, aux)
    except kernel.NumbaError:
        return render_arr(arr_srgb, analysis)


def warmup() -> None:
    """用极小 dummy 图提前触发 JIT 与磁盘 cache。"""

    dummy = np.full((4, 4, 3), 0.5, dtype=np.float32)
    render_fused(
        dummy,
        {
            "basic": {"exposure": 0.01},
            "tone_curve": [],
            "hsl": [],
            "color_grading": {},
            "effects": {},
        },
    )


def _to_arr(image: Image.Image) -> np.ndarray:
    if image.mode != "RGB":
        image = image.convert("RGB")
    return np.asarray(image, dtype=np.float32) / 255.0


def _to_image(arr: np.ndarray) -> Image.Image:
    pixels = (np.clip(arr, 0, 1) * 255.0 + 0.5).astype(np.uint8)
    return Image.fromarray(pixels, "RGB")


def render_proxy(image: Image.Image, analysis: dict) -> Image.Image:
    """长边不超过 2048 的交互代理入口。"""

    proxy = image.copy()
    proxy.thumbnail((_PROXY_LONG_EDGE, _PROXY_LONG_EDGE), Image.Resampling.LANCZOS)
    return _to_image(render_fused(_to_arr(proxy), analysis))


def render_full(image: Image.Image, analysis: dict) -> Image.Image:
    """保持原尺寸的全分辨率融合入口。"""

    return _to_image(render_fused(_to_arr(image), analysis))


def prepare_aux(arr_srgb: np.ndarray, analysis: dict) -> AuxBuffers:
    """生成一次 S2 辅助缓冲；analysis 预留给后续空间参数缓存键。"""

    del analysis
    source = np.ascontiguousarray(arr_srgb, dtype=np.float32)
    luma = (
        source[..., 0] * 0.2126
        + source[..., 1] * 0.7152
        + source[..., 2] * 0.0722
    ).astype(np.float32)
    return AuxBuffers(*kernel.build_aux(luma))


def render_with_aux(
    arr_srgb: np.ndarray, analysis: dict, aux: AuxBuffers
) -> np.ndarray:
    """复用已准备 S2，仅重跑融合内核。"""

    return render_fused(arr_srgb, analysis, aux)
