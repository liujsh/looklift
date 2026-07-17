"""Operator 协议、Stage/Domain、扁平 ResolvedParams 暂存 + 稳定 enable 位掩码。

单一数学、两处形态：apply_px（numba device 函数，被融合内核 inline，生产路径）与
apply_numpy（向量化参考，op 单测 / LUT 采样 / numba 兜底）。二者一致性由「融合前后
一致」测试（容差 ≤1/255）守护。operator 是组织/契约/测试层，融合内核是执行层。
"""
from __future__ import annotations

from enum import Enum, IntEnum
from numbers import Number
from typing import Protocol, runtime_checkable

import numpy as np


class Stage(IntEnum):
    """固定命名阶段序列（镜像 AlcedoStudio，非节点图）。"""

    INGEST = 0  # S0 PIL→float32、mode 归一、代理缩图
    TO_WORKING = 1  # S1 sRGB(display)→linear
    PREPASS = 2  # S2 辅助缓冲（模糊亮度/局部对比/噪声场/曲线烘 LUT）
    FUSED = 3  # S3 单遍融合色彩 op
    OUTPUT = 4  # S4 display→sRGB 输出、grain 叠加、嵌 ICC、编码回 PIL


class Domain(Enum):
    """op 执行的光域。物理合并运算在 LINEAR，LR 滑杆语义在 DISPLAY。"""

    LINEAR = "linear"
    DISPLAY = "display"


# 各 op 的 enable 位（位唯一；融合内核里 0 值 op 用 if 短路）。
# 顺序即 §2.3 单管线光域切换顺序：只有 exposure/WB 在 linear，其余在 display；
# grain 仅保留 S4 参数位，不得进入 fused 主体。
_OP_ORDER = (
    "exposure",
    "white_balance",
    "contrast",
    "highlights_shadows",
    "whites_blacks",
    "tone_curve",
    "hsl",
    "saturation",
    "color_grading",
    "texture",
    "clarity",
    "dehaze",
    "vignette",
    "grain",
)
OP_BITS: dict[str, int] = {name: 1 << i for i, name in enumerate(_OP_ORDER)}


@runtime_checkable
class Operator(Protocol):
    """所有渲染 operator 共同遵循的组织与参考实现契约。"""

    name: str
    stage: Stage
    domain: Domain

    def resolve(self, analysis: dict) -> tuple | None:
        """切出本 op 参数分片并预计算；全 0（无效）返回 None。"""
        ...

    def apply_numpy(
        self, arr: np.ndarray, params: tuple, aux=None
    ) -> np.ndarray:
        """整数组参考实现；与 apply_px 是同一数学的两种写法。"""
        ...

    def apply_px(
        self, r: float, g: float, b: float, *params, aux=None
    ) -> tuple[float, float, float]:
        """逐像素实现，由生产融合内核内联调用。"""
        ...


def _validate_leaf(value) -> None:
    """只接受数值标量或 1D、C 连续的 float32 定长数组。"""
    if isinstance(value, (Number, np.number)):
        return
    if isinstance(value, np.ndarray):
        if value.ndim == 1 and value.dtype == np.float32 and value.flags.c_contiguous:
            return
        raise TypeError("数组参数必须是 1D、C-contiguous 的 np.float32")
    raise TypeError("参数叶子必须是数值标量或定长 np.float32 一维数组")


class ResolvedParams:
    """operator resolve 结果的扁平 Python 暂存：op 名 → tuple + enable。

    tuple 叶子只能是 Python/NumPy 数值标量，或 1D、C 连续的 float32 定长数组；
    容器、object、错误 dtype/维度/连续性的数组均拒绝。本结构供 numpy 参考路径
    与 T6b marshal 使用，融合内核不得直接接收它。
    """

    __slots__ = ("_params", "enable")

    def __init__(self) -> None:
        self._params: dict[str, tuple] = {}
        self.enable: int = 0

    @classmethod
    def pack(cls, op_results: dict[str, tuple | None]) -> ResolvedParams:
        """校验并打包各 op 结果，为非 None 结果设置 enable 位。"""
        rp = cls()
        for name, result in op_results.items():
            if result is None:
                continue
            if not isinstance(result, tuple):
                raise TypeError("operator 参数必须是 tuple")
            for value in result:
                _validate_leaf(value)
            rp._params[name] = result
            rp.enable |= OP_BITS[name]
        return rp

    def is_enabled(self, name: str) -> bool:
        """返回指定 op 的 enable 位是否已设置。"""
        return bool(self.enable & OP_BITS[name])

    def get(self, name: str) -> tuple | None:
        """返回指定 op 的预计算参数；未启用时返回 None。"""
        return self._params.get(name)
