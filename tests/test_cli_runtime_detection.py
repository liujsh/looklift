from __future__ import annotations

import subprocess

from looklift.builtin_runtimes import builtin_runtime_registry
from looklift.cli_runtime_detection import detect_cli_runtime


def test_cli_detection_returns_version_without_exposing_executable_path() -> None:
    result = detect_cli_runtime(
        builtin_runtime_registry().get("codex-cli"),
        executable_resolver=lambda _command: "C:/secret/home/codex.exe",
        runner=lambda *args, **kwargs: subprocess.CompletedProcess(
            args[0], 0, stdout="codex 1.2.3\n", stderr=""
        ),
    )

    assert result.available is True
    assert result.version == "codex 1.2.3"
    assert "C:/secret" not in str(result)
