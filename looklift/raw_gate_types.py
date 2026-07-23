"""RAW 门的最小解码结果类型。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class DecodedRaw:
    rgb: Any
    orientation: str
    white_balance_checked: bool
