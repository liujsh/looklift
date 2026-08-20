"""Pi CLI 的能力探测与最小权限启动封套。"""

from __future__ import annotations

import json
import os
import re
import shutil
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
PiSupportTier = Literal["supported", "unsupported"]
ProbeRunner = Callable[[Sequence[str]], subprocess.CompletedProcess[str]]
PiExecutable = str | Sequence[str]
PiLaunchResolver = Callable[
    [AgentRunInput, CliWorkspace, str, str],
    "PiLaunchSpec",
]


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
    executable: PiExecutable = "pi",
    *,
    runner: ProbeRunner | None = None,
) -> PiProbeResult:
    """探测版本与安全启动形态；真实链路证据记录在 v2.6 开发日志。"""
    run = runner or _run_probe
    try:
        command = resolve_pi_command(executable)
        completed = run((*command, "--version"))
    except (OSError, subprocess.SubprocessError, ValueError):
        return PiProbeResult(False, None, "unsupported", "未找到可执行的 Pi CLI")
    version = _parse_version(completed.stdout)
    if completed.returncode != 0 or version is None:
        return PiProbeResult(False, None, "unsupported", "Pi CLI 版本输出无效")
    if version < _MINIMUM_VERSION:
        return PiProbeResult(True, version, "unsupported", "Pi CLI 版本缺少所需隔离参数")
    return PiProbeResult(
        True,
        version,
        "supported",
        "具备 RPC 事件、禁用内建工具、单扩展加载和真实图片反馈能力",
    )


def prepare_pi_launch(
    *,
    executable: PiExecutable,
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
        *_command_prefix(executable),
        "--mode",
        "rpc",
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


def build_pi_launch_resolver(*, executable: PiExecutable = "pi") -> PiLaunchResolver:
    """装配使用随应用发布扩展的生产 Pi 启动解析器。"""
    extension = Path(__file__).parent / "data" / "cli" / "pi-looklift-tools.js"
    command = resolve_pi_command(executable)

    def resolve(
        run_input: AgentRunInput,
        workspace: CliWorkspace,
        gateway_url: str,
        token: str,
    ) -> PiLaunchSpec:
        return prepare_pi_launch(
            executable=command,
            run_input=run_input,
            workspace=workspace,
            extension_path=extension,
            gateway_url=gateway_url,
            token=token,
            source_environment=os.environ,
        )

    return resolve


def resolve_pi_command(
    executable: PiExecutable = "pi",
    *,
    platform: str = os.name,
    which: Callable[[str], str | None] = shutil.which,
) -> tuple[str, ...]:
    """Windows npm shim 改为直启 Node，保证取消回收的是实际 Pi 进程。"""
    prefix = _command_prefix(executable)
    if len(prefix) != 1 or platform != "nt":
        return prefix

    requested = prefix[0]
    resolved = Path(requested)
    if not resolved.is_file():
        found = which(requested)
        if found is None and not Path(requested).suffix:
            found = which(f"{requested}.cmd")
        if found is None:
            return prefix
        resolved = Path(found)
    if resolved.suffix.casefold() not in {".cmd", ".ps1"}:
        return (str(resolved),)

    package_roots = (
        ("@earendil-works", "pi-coding-agent"),
        ("@mariozechner", "pi-coding-agent"),
    )
    cli_script = next(
        (
            resolved.parent / "node_modules" / scope / package / "dist" / "cli.js"
            for scope, package in package_roots
            if (
                resolved.parent / "node_modules" / scope / package / "dist" / "cli.js"
            ).is_file()
        ),
        None,
    )
    bundled_node = resolved.parent / "node.exe"
    node_path = str(bundled_node) if bundled_node.is_file() else which("node")
    if cli_script is None or node_path is None:
        raise ValueError("无法安全解析 Windows Pi npm 包装器")
    return node_path, str(cli_script)


def _command_prefix(executable: PiExecutable) -> tuple[str, ...]:
    if isinstance(executable, str):
        prefix = (executable,)
    else:
        prefix = tuple(executable)
    if not prefix or any(not isinstance(part, str) or not part.strip() for part in prefix):
        raise ValueError("Pi 启动命令不能为空")
    return prefix


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
