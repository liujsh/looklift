"""Numba 可选依赖适配；缺失时保留可运行的纯 Python/NumPy 路径。"""
from __future__ import annotations

try:
    from numba import njit, prange
    from numba.core.errors import NumbaError
    from numba.extending import register_jitable

    HAS_NUMBA = True
except ImportError:  # pragma: no cover - 由 monkeypatch 兜底测试覆盖调用分支
    HAS_NUMBA = False
    prange = range

    class NumbaError(Exception):
        """无 numba 环境中的兼容异常基类。"""

    def njit(*args, **kwargs):
        """缺少 numba 时退化为原 Python 函数。"""

        if args and callable(args[0]):
            return args[0]

        def decorator(function):
            return function

        return decorator

    def register_jitable(*args, **kwargs):
        """缺少 numba 时保留标量函数可调用。"""

        if args and callable(args[0]):
            return args[0]

        def decorator(function):
            return function

        return decorator
