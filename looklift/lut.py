"""把 analysis 的全局色彩映射采样成 3D LUT(.cube,Resolve 规范)。

暗角/颗粒是空间效果,LUT 无法承载,导出时跳过(CLI 层提示)。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from .render import _apply_color_ops


def export_cube(analysis: dict, out: str | Path, size: int = 33) -> Path:
    ax = np.linspace(0.0, 1.0, size, dtype=np.float32)
    # .cube 行序:R 变化最快,然后 G,最后 B
    b, g, r = np.meshgrid(ax, ax, ax, indexing="ij")
    grid = np.stack([r, g, b], axis=-1).reshape(-1, 1, 3)  # (N,1,3) 伪图像
    mapped = _apply_color_ops(grid, analysis).reshape(-1, 3)

    lines = [
        f'TITLE "looklift"',
        f"LUT_3D_SIZE {size}",
        "DOMAIN_MIN 0.0 0.0 0.0",
        "DOMAIN_MAX 1.0 1.0 1.0",
    ]
    lines += [f"{p[0]:.6f} {p[1]:.6f} {p[2]:.6f}" for p in mapped]
    out = Path(out)
    out.write_text("\n".join(lines) + "\n", encoding="ascii")
    return out
