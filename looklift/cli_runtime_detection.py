"""本机 CLI Runtime 的限时、脱敏探测。"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Callable

from .runtime_registry import RuntimeDefinition


@dataclass(frozen=True)
class CliRuntimeDetection:
    runtime_id: str
    available: bool
    authenticated: bool = False
    version: str | None = None
    models: tuple[str, ...] = ()
    error: str | None = None


def detect_cli_runtime(
    definition: RuntimeDefinition,
    *,
    executable_resolver: Callable[[str], str | None] = shutil.which,
    runner=subprocess.run,
) -> CliRuntimeDetection:
    if definition.kind != "cli" or definition.command is None:
        return CliRuntimeDetection(
            definition.runtime_id, False, error="Runtime 不是 CLI"
        )
    executable = executable_resolver(definition.command)
    if executable is None:
        return CliRuntimeDetection(
            definition.runtime_id, False, error="未安装或不在 PATH"
        )
    try:
        completed = runner(
            [executable, "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError
        version = completed.stdout.strip().splitlines()[0][:120]
        return CliRuntimeDetection(
            definition.runtime_id,
            True,
            authenticated=True,
            version=version or None,
            models=definition.models,
        )
    except Exception:
        return CliRuntimeDetection(
            definition.runtime_id, False, error="Runtime 探测失败"
        )
