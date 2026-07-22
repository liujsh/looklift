"""Windows 文件管理器边界；业务层只传已校验的本地路径。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def reveal_in_explorer(path: Path) -> None:
    source = Path(path).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if sys.platform != "win32":
        raise OSError("当前系统不支持 Windows Explorer")
    subprocess.Popen(["explorer.exe", "/select,", str(source)])  # noqa: S603,S607
