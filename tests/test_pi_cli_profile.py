"""Pi CLI 能力探测与最小权限启动参数。"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from looklift.agent_adapter import AgentImage, AgentRunInput
from looklift.cli_workspace import CliWorkspaceManager
from looklift.domain_pack_types import CompiledDomainPack
from looklift.pi_cli_profile import (
    build_pi_launch_resolver,
    prepare_pi_launch,
    probe_pi,
    resolve_pi_command,
)


def _run_input() -> AgentRunInput:
    return AgentRunInput(
        run_id="run-pi",
        attempt_id="attempt-pi",
        domain_pack=CompiledDomainPack(
            instructions="只允许候选工具。",
            user_message="提亮照片",
            source_hashes=(),
            omitted_sources=(),
            content_hash="c" * 64,
            estimated_tokens=8,
        ),
        proxy_image=AgentImage("image/jpeg", b"\xff\xd8proxy\xff\xd9"),
        model="provider/model",
    )


def test_probe_marks_verified_version_as_supported() -> None:
    def runner(_command):
        return subprocess.CompletedProcess([], 0, stdout="0.84.1\n", stderr="")

    result = probe_pi(runner=runner)

    assert result.available is True
    assert result.version == (0, 84, 1)
    assert result.tier == "supported"


def test_probe_rejects_missing_or_old_pi() -> None:
    def missing(_command):
        raise FileNotFoundError

    def old(_command):
        return subprocess.CompletedProcess([], 0, stdout="0.70.0", stderr="")

    assert probe_pi(runner=missing).tier == "unsupported"
    assert probe_pi(runner=old).tier == "unsupported"


def test_prepare_pi_launch_disables_all_unselected_capabilities(tmp_path: Path) -> None:
    workspace = CliWorkspaceManager(tmp_path / "workspace").create(_run_input())
    extension = tmp_path / "readonly" / "pi-looklift-tools.js"
    extension.parent.mkdir()
    extension.write_text("export default () => {};", encoding="utf-8")

    launch = prepare_pi_launch(
        executable="pi",
        run_input=_run_input(),
        workspace=workspace,
        extension_path=extension,
        gateway_url="http://127.0.0.1:43123",
        token="opaque-token",
        source_environment={"PATH": "tools", "OPENAI_API_KEY": "must-drop"},
    )

    for flag in (
        "--no-session",
        "--no-approve",
        "--no-builtin-tools",
        "--no-extensions",
        "--no-skills",
        "--no-prompt-templates",
        "--no-themes",
        "--no-context-files",
    ):
        assert flag in launch.command
    mode_index = launch.command.index("--mode") + 1
    assert launch.command[mode_index] == "rpc"
    assert "@DOMAIN_PACK.md" not in launch.command
    assert "@proxy.jpg" not in launch.command
    assert "run-pi" not in " ".join(launch.command)
    assert "attempt-pi" not in " ".join(launch.command)
    assert launch.environment["LOOKLIFT_TOOL_TOKEN"] == "opaque-token"
    assert launch.environment["PI_TELEMETRY"] == "0"
    assert launch.environment["PI_SKIP_VERSION_CHECK"] == "1"
    assert "OPENAI_API_KEY" not in launch.environment
    assert (workspace.path / "tool-schema.json").is_file()


def test_packaged_launch_resolver_uses_readonly_extension_and_current_environment(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = CliWorkspaceManager(tmp_path / "workspace").create(_run_input())
    monkeypatch.setenv("PATH", "pi-tools")
    monkeypatch.setenv("OPENAI_API_KEY", "must-drop")

    launch = build_pi_launch_resolver(executable="pi")(
        _run_input(),
        workspace,
        "http://127.0.0.1:43123",
        "opaque-token",
    )

    extension_index = launch.command.index("--extension") + 1
    extension = Path(launch.command[extension_index])
    assert extension.name == "pi-looklift-tools.js"
    assert extension.is_file()
    assert not extension.is_relative_to(workspace.path)
    assert launch.environment["PATH"] == "pi-tools"
    assert "OPENAI_API_KEY" not in launch.environment


def test_launch_resolver_accepts_direct_node_command_prefix(tmp_path: Path) -> None:
    workspace = CliWorkspaceManager(tmp_path / "workspace").create(_run_input())
    resolver = build_pi_launch_resolver(
        executable=("node", "C:/readonly/pi/dist/cli.js")
    )

    launch = resolver(
        _run_input(),
        workspace,
        "http://127.0.0.1:43123",
        "opaque-token",
    )

    assert launch.command[:2] == ("node", "C:/readonly/pi/dist/cli.js")


def test_resolve_pi_command_bypasses_windows_npm_wrapper(tmp_path: Path) -> None:
    root = tmp_path / "node"
    shim = root / "pi.cmd"
    node = root / "node.exe"
    cli = (
        root
        / "node_modules"
        / "@earendil-works"
        / "pi-coding-agent"
        / "dist"
        / "cli.js"
    )
    cli.parent.mkdir(parents=True)
    shim.write_text("npm shim", encoding="utf-8")
    node.write_bytes(b"node")
    cli.write_text("pi", encoding="utf-8")

    command = resolve_pi_command(str(shim), platform="nt")

    assert command == (str(node), str(cli))


def test_prepare_pi_launch_rejects_extension_in_writable_workspace(
    tmp_path: Path,
) -> None:
    workspace = CliWorkspaceManager(tmp_path).create(_run_input())
    extension = workspace.path / "extension.js"
    extension.write_text("export default () => {};", encoding="utf-8")

    with pytest.raises(ValueError, match="只读目录"):
        prepare_pi_launch(
            executable="pi",
            run_input=_run_input(),
            workspace=workspace,
            extension_path=extension,
            gateway_url="http://127.0.0.1:43123",
            token="opaque-token",
            source_environment={},
        )


@pytest.mark.parametrize(
    "url",
    ["https://127.0.0.1:43123", "http://example.com:43123", "http://127.0.0.1"],
)
def test_prepare_pi_launch_rejects_non_loopback_gateway(
    tmp_path: Path,
    url: str,
) -> None:
    workspace = CliWorkspaceManager(tmp_path / "workspace").create(_run_input())
    extension = tmp_path / "extension.js"
    extension.write_text("export default () => {};", encoding="utf-8")

    with pytest.raises(ValueError, match="Gateway"):
        prepare_pi_launch(
            executable="pi",
            run_input=_run_input(),
            workspace=workspace,
            extension_path=extension,
            gateway_url=url,
            token="opaque-token",
            source_environment={},
        )
