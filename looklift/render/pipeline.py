"""分阶段渲染编排；提供线性光与 display 域 NumPy 参考串联。"""
from __future__ import annotations

import numpy as np

from . import color_space as cs
from .base import ResolvedParams
from .operators import REGISTRY


def resolve_params(analysis: dict) -> ResolvedParams:
    """遍历注册表一次解析参数，生成共用的扁平暂存。"""
    return ResolvedParams.pack(
        {operator.name: operator.resolve(analysis) for operator in REGISTRY}
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
