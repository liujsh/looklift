"""Pi CLI 的能力探测与最小权限启动封套。"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from .agent_adapter import AgentRunInput
from .cli_workspace import CliWorkspace, sanitized_cli_environment
from .scoped_tool_gateway import agent_tool_definitions


_VERSION_PATTERN = re.compile(r"(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)")
_MINIMUM_VERSION = (0, 84, 0)
PiSupportTier = Literal["candidate", "unsupported"]
ProbeRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]


@dataclass(frozen=True)
class PiProbeResult:
    available: bool
    version: tuple[int, int, int] | None
    tier: PiSupportTier
    reason: str


@dataclass(frozen=True)
class PiLaunchSpec:
    command: tuple[str, ...]
    environment: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "environment", dict(self.environment))


def probe_pi(
    executable: str = "pi",
    *,
    runner: ProbeRunner | None = None,
) -> PiProbeResult:
    """探测只读取版本；candidate 仍需真实图片与取消人工验收。"""
    run = runner or _run_probe
    try:
        completed = run((executable, "--version"))
    except (OSError, subprocess.SubprocessError):
        return PiProbeResult(False, None, "unsupported", "未找到可执行的 Pi CLI")
    version = _parse_version(completed.stdout)
    if completed.returncode != 0 or version is None:
        return PiProbeResult(False, None, "unsupported", "Pi CLI 版本输出无效")
    if version < _MINIMUM_VERSION:
        return PiProbeResult(True, version, "unsupported", "Pi CLI 版本缺少所需隔离参数")
    return PiProbeResult(
        True,
        version,
        "candidate",
        "具备 JSON 事件、禁用内建工具和单扩展加载能力，仍待真实集成验收",
    )


def prepare_pi_launch(
    *,
    executable: str,
    run_input: AgentRunInput,
    workspace: CliWorkspace,
    extension_path: Path,
    gateway_url: str,
    token: str,
    source_environment: Mapping[str, str],
) -> PiLaunchSpec:
    """生成不依赖用户项目资源的 Pi 单次 JSON 运行规格。"""
    extension = extension_path.resolve()
    if not extension.is_file():
        raise ValueError("Pi 扩展文件不存在")
    if extension.is_relative_to(workspace.path.resolve()):
        raise ValueError("Pi 扩展必须来自随应用只读目录，不能位于 Workspace")
    _validate_loopback_url(gateway_url)
    if not token:
        raise ValueError("Scoped Tool Token 不能为空")

    schema_path = workspace.path / "tool-schema.json"
    schema_path.write_text(
        json.dumps(agent_tool_definitions(), ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    command = (
        executable,
        "--mode",
        "json",
        "--no-session",
        "--no-approve",
        "--no-builtin-tools",
        "--no-extensions",
        "--extension",
        str(extension),
        "--no-skills",
        "--no-prompt-templates",
        "--no-themes",
        "--no-context-files",
        "--model",
        run_input.model,
        "@DOMAIN_PACK.md",
        "@proxy.jpg",
        "依据领域契约生成候选，并以 finish_candidate 结束。",
    )
    environment = sanitized_cli_environment(source_environment)
    environment.update(
        {
            "LOOKLIFT_GATEWAY_URL": gateway_url,
            "LOOKLIFT_TOOL_TOKEN": token,
            "LOOKLIFT_TOOL_SCHEMA_FILE": "tool-schema.json",
            "PI_TELEMETRY": "0",
            "PI_SKIP_VERSION_CHECK": "1",
        }
    )
    return PiLaunchSpec(command=command, environment=environment)


def _parse_version(value: str) -> tuple[int, int, int] | None:
    match = _VERSION_PATTERN.search(value)
    if match is None:
        return None
    return tuple(int(match.group(name)) for name in ("major", "minor", "patch"))


def _run_probe(command: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        capture_output=True,
        check=False,
        text=True,
        timeout=5,
    )


def _validate_loopback_url(value: str) -> None:
    parsed = urlparse(value)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Tool Gateway 必须是本机 HTTP 地址")
    if parsed.port is None:
        raise ValueError("Tool Gateway 必须使用显式随机端口")
