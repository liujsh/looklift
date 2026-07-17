"""sRGB 与线性光的精确传递函数，以及 sRGB ICC 嵌入封装。

当前仅支持 sRGB。Display-P3 基色转换留待后续版本；即使 pyvips 或其动态库
不可用，核心数学与 Pillow 导出的 ICC 嵌入仍可独立工作。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import numpy as np
from PIL import Image

try:  # pyvips 是可选能力，导入时也可能因 libvips 动态库缺失而失败
    import pyvips  # noqa: F401

    HAS_PYVIPS = True
except Exception:
    HAS_PYVIPS = False


_ICC_PATH = Path(__file__).with_name("data") / "sRGB-IEC61966-2.1.icc"


def srgb_to_linear(arr: np.ndarray) -> np.ndarray:
    """将 sRGB 显示编码值转换为线性光，使用精确分段 EOTF。"""

    values = arr.astype(np.float32)
    return np.where(
        values <= 0.04045,
        values / 12.92,
        np.power((values + 0.055) / 1.055, 2.4),
    ).astype(np.float32)


def linear_to_srgb(arr: np.ndarray) -> np.ndarray:
    """将线性光转换为 sRGB 显示编码值，使用精确分段 OETF。"""

    values = arr.astype(np.float32)
    return np.where(
        values <= 0.0031308,
        values * 12.92,
        1.055 * np.power(np.clip(values, 0.0, None), 1.0 / 2.4) - 0.055,
    ).astype(np.float32)


@lru_cache(maxsize=1)
def srgb_icc_bytes() -> bytes:
    """读取并缓存随包发布的标准 sRGB ICC profile。"""

    return _ICC_PATH.read_bytes()


def embed_icc(image: Image.Image) -> dict[str, bytes]:
    """返回可直接传给 ``Image.save`` 的 sRGB ICC 参数。"""

    return {"icc_profile": srgb_icc_bytes()}
