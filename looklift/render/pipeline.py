"""分阶段渲染编排；本模块先提供 display 域 NumPy 参考串联。"""
from __future__ import annotations

import numpy as np

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

    for name in ("tone_curve", "hsl", "saturation", "color_grading"):
        params = resolved.get(name)
        if params is not None:
            arr = operators[name].apply_numpy(arr, params)

    return np.clip(arr, 0, 1).astype(np.float32)
