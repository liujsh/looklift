"""Fake CLI 进程对统一 Adapter ABI 的离线契约测试。"""

from __future__ import annotations

import asyncio
import sys
from copy import deepcopy
from pathlib import Path

from PIL import Image

from looklift.agent_adapter import AgentEventKind, AgentImage, AgentRunInput
from looklift.candidate_runtime import CandidateRuntime
from looklift.candidate_runtime_types import InMemoryRunAuthority, RunBinding
from looklift.cli_agent_adapter import JsonlCliAgentAdapter
from looklift.cli_workspace import CliWorkspaceManager
from looklift.domain_pack_types import CompiledDomainPack


class FakeRenderer:
    def render(self, _image_path: Path, _analysis: dict) -> bytes:
        from io import BytesIO

        output = BytesIO()
        Image.new("RGB", (8, 8), (140, 140, 140)).save(output, format="JPEG")
        return output.getvalue()


def _run_input() -> AgentRunInput:
    return AgentRunInput(
        run_id="run-cli",
        attempt_id="attempt-cli",
        domain_pack=CompiledDomainPack(
            instructions="只允许生成候选。",
            user_message="自然提亮当前照片",
            source_hashes=(),
            omitted_sources=(),
            content_hash="b" * 64,
            estimated_tokens=12,
        ),
        proxy_image=AgentImage("image/jpeg", b"\xff\xd8proxy\xff\xd9"),
        model="fake-cli",
    )


def _runtime(sample_analysis: dict) -> CandidateRuntime:
    binding = RunBinding(
        run_id="run-cli",
        attempt_id="attempt-cli",
        lease="lease-cli",
        base_version_id="version-cli",
        image_path=Path(__file__),
    )
    return CandidateRuntime(
        binding=binding,
        authority=InMemoryRunAuthority(binding),
        baseline_analysis=deepcopy(sample_analysis),
        renderer=FakeRenderer(),
    )


def _command(mode: str) -> tuple[str, ...]:
    fixture = Path(__file__).parent / "fixtures" / "fake_agent_cli.py"
    return sys.executable, "-u", str(fixture), mode


def test_fake_cli_completes_candidate_loop_and_image_feedback(
    sample_analysis: dict,
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "must-not-leak")
    runtime = _runtime(sample_analysis)
    adapter = JsonlCliAgentAdapter(
        command_resolver=lambda _input: _command("candidate"),
        runtime_resolver=lambda _input: runtime,
        workspace_manager=CliWorkspaceManager(tmp_path),
    )

    async def exercise():
        return [event async for event in adapter.start(_run_input())]

    events = asyncio.run(exercise())

    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert AgentEventKind.CANDIDATE_CREATED in [event.kind for event in events]
    assert events[-1].kind is AgentEventKind.RUN_FINISHED
    assert events[-1].payload["outcome"] == "candidate_ready"
    text_event = next(event for event in events if event.kind is AgentEventKind.TEXT_DELTA)
    assert text_event.payload["text"] == "workspace-ok:True:False"
    assert runtime.finished is not None


def test_cli_cancel_revokes_runtime_and_reaps_process(
    sample_analysis: dict,
    tmp_path: Path,
) -> None:
    runtime = _runtime(sample_analysis)
    adapter = JsonlCliAgentAdapter(
        command_resolver=lambda _input: _command("slow"),
        runtime_resolver=lambda _input: runtime,
        workspace_manager=CliWorkspaceManager(tmp_path),
        cancel_grace_seconds=0.2,
    )

    async def exercise():
        stream = adapter.start(_run_input())
        started = await anext(stream)
        text = await anext(stream)
        pending = asyncio.create_task(anext(stream))
        await adapter.cancel("run-cli")
        terminal = await asyncio.wait_for(pending, timeout=1)
        return started, text, terminal

    started, text, terminal = asyncio.run(exercise())

    assert started.kind is AgentEventKind.RUN_STARTED
    assert text.kind is AgentEventKind.TEXT_DELTA
    assert terminal.kind is AgentEventKind.RUN_FINISHED
    assert terminal.payload["outcome"] == "cancelled"
    assert adapter.active_process_count == 0


def test_malformed_cli_output_fails_without_echoing_payload(
    sample_analysis: dict,
    tmp_path: Path,
) -> None:
    adapter = JsonlCliAgentAdapter(
        command_resolver=lambda _input: _command("broken"),
        runtime_resolver=lambda _input: _runtime(sample_analysis),
        workspace_manager=CliWorkspaceManager(tmp_path),
    )

    async def exercise():
        return [event async for event in adapter.start(_run_input())]

    events = asyncio.run(exercise())

    assert events[-1].kind is AgentEventKind.RUN_FAILED
    assert events[-1].payload == {
        "code": "cli_protocol_failed",
        "message": "本地 CLI 返回了无效事件",
    }
