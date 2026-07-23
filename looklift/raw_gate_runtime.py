"""RAW 门运行时适配：可选 rawpy 解码与平台内存测量。"""
from __future__ import annotations

import ctypes
import os

try:
    import resource
except ImportError:  # pragma: no cover - Windows uses GetProcessMemoryInfo
    resource = None

from typing import Callable
from pathlib import Path

from .raw_gate_types import DecodedRaw


def load_rawpy_decoder() -> tuple[Callable[[Path], DecodedRaw] | None, str | None]:
    try:
        import rawpy  # type: ignore[import-not-found]
    except (ImportError, OSError):
        return None, "rawpy_unavailable"

    def decode(path: Path) -> DecodedRaw:
        with rawpy.imread(str(path)) as raw:
            rgb = raw.postprocess(
                output_bps=16,
                use_camera_wb=True,
                no_auto_bright=True,
                output_color=rawpy.ColorSpace.sRGB,
            )
            flip = getattr(getattr(raw, "sizes", None), "flip", 0)
            orientation = "normal" if flip in (0, None) else "camera"
        return DecodedRaw(rgb=rgb, orientation=orientation, white_balance_checked=True)

    return decode, None


def measure_memory_mb() -> float | None:
    if os.name == "nt":
        class ProcessMemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", ctypes.c_ulong),
                ("PageFaultCount", ctypes.c_ulong),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = ProcessMemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        process = ctypes.windll.kernel32.GetCurrentProcess()
        get_info = ctypes.windll.psapi.GetProcessMemoryInfo
        get_info.argtypes = [ctypes.c_void_p, ctypes.POINTER(ProcessMemoryCounters), ctypes.c_ulong]
        get_info.restype = ctypes.c_bool
        if get_info(process, ctypes.byref(counters), counters.cb):
            return counters.PeakWorkingSetSize / (1024 * 1024)
        return None
    if resource is None:
        return None
    try:
        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return value / (1024 * 1024) if value > 1024 * 1024 else value / 1024
    except (AttributeError, OSError):
        return None
