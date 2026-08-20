"""CLI Attempt 隔离 Workspace 与环境清理。"""

from __future__ import annotations

from pathlib import Path

from looklift.agent_adapter import AgentImage, AgentRunInput
from looklift.cli_workspace import CliWorkspaceManager, sanitized_cli_environment
from looklift.domain_pack_types import CompiledDomainPack


def _run_input() -> AgentRunInput:
    return AgentRunInput(
        run_id="private-run",
        attempt_id="private-attempt",
        domain_pack=CompiledDomainPack(
            instructions="只允许生成候选。",
            user_message="自然提亮当前照片",
            source_hashes=(),
            omitted_sources=(),
            content_hash="a" * 64,
            estimated_tokens=12,
        ),
        proxy_image=AgentImage("image/jpeg", b"\xff\xd8proxy\xff\xd9"),
        model="fake-cli",
    )


def test_workspace_contains_only_compiled_context_proxy_and_candidates(
    tmp_path: Path,
) -> None:
    manager = CliWorkspaceManager(tmp_path)
    lease = manager.create(_run_input())

    assert {path.name for path in lease.path.iterdir()} == {
        "DOMAIN_PACK.md",
        "proxy.jpg",
        "candidates",
    }
    assert "自然提亮当前照片" in lease.domain_pack_path.read_text(encoding="utf-8")
    assert lease.proxy_path.read_bytes() == b"\xff\xd8proxy\xff\xd9"
    assert "private-run" not in str(lease.path)
    assert "private-attempt" not in str(lease.path)

    manager.dispose(lease)
    assert not lease.path.exists()


def test_cli_environment_keeps_operational_values_but_removes_secrets() -> None:
    source = {
        "PATH": "tools",
        "SystemRoot": "windows",
        "TEMP": "temp",
        "ANTHROPIC_API_KEY": "secret-a",
        "OPENAI_API_KEY": "secret-b",
        "LOOKLIFT_SECRET": "secret-c",
        "DATABASE_URL": "secret-d",
        "UNRELATED": "drop-me",
    }

    cleaned = sanitized_cli_environment(source)

    assert cleaned["PATH"] == "tools"
    assert cleaned["SystemRoot"] == "windows"
    assert cleaned["PYTHONIOENCODING"] == "utf-8"
    assert not {"ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LOOKLIFT_SECRET", "DATABASE_URL"} & cleaned.keys()
    assert "UNRELATED" not in cleaned
