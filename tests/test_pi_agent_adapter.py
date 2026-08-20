"""Pi 原生 JSON 事件到统一 Adapter ABI 的离线闭环。"""

from __future__ import annotations

import asyncio
import os
import sys
from copy import deepcopy
from pathlib import Path

from PIL import Image

from looklift.agent_adapter import AgentEventKind, AgentImage, AgentRunInput
from looklift.candidate_runtime import CandidateRuntime
from looklift.candidate_runtime_types import InMemoryRunAuthority, RunBinding
from looklift.cli_workspace import CliWorkspaceManager, sanitized_cli_environment
from looklift.domain_pack_types import CompiledDomainPack
from looklift.pi_agent_adapter import PiAgentAdapter
from looklift.pi_cli_profile import PiLaunchSpec


class FakeRenderer:
    def render(self, _image_path: Path, _analysis: dict) -> bytes:
        from io import BytesIO

        output = BytesIO()
        Image.new("RGB", (8, 8), (145, 145, 145)).save(output, format="JPEG")
        return output.getvalue()


def _run_input() -> AgentRunInput:
    return AgentRunInput(
        run_id="run-pi",
        attempt_id="attempt-pi",
        domain_pack=CompiledDomainPack(
            instructions="只允许候选工具。",
            user_message="提亮照片",
            source_hashes=(),
            omitted_sources=(),
            content_hash="d" * 64,
            estimated_tokens=8,
        ),
        proxy_image=AgentImage("image/jpeg", b"\xff\xd8proxy\xff\xd9"),
        model="fake-pi-model",
    )


def _runtime(sample_analysis: dict) -> CandidateRuntime:
    binding = RunBinding(
        run_id="run-pi",
        attempt_id="attempt-pi",
        lease="lease-pi",
        base_version_id="version-pi",
        image_path=Path(__file__),
    )
    return CandidateRuntime(
        binding=binding,
        authority=InMemoryRunAuthority(binding),
        baseline_analysis=deepcopy(sample_analysis),
        renderer=FakeRenderer(),
    )


def _resolver(mode: str):
    fixture = Path(__file__).parent / "fixtures" / "fake_pi_cli.py"

    def resolve(_input, _workspace, gateway_url: str, token: str) -> PiLaunchSpec:
        environment = sanitized_cli_environment(os.environ)
        environment.update(
            {
                "LOOKLIFT_GATEWAY_URL": gateway_url,
                "LOOKLIFT_TOOL_TOKEN": token,
            }
        )
        return PiLaunchSpec(
            command=(sys.executable, "-u", str(fixture), mode),
            environment=environment,
        )

    return resolve


def test_pi_adapter_normalizes_native_events_and_runtime_facts(
    sample_analysis: dict,
    tmp_path: Path,
) -> None:
    runtime = _runtime(sample_analysis)
    adapter = PiAgentAdapter(
        launch_resolver=_resolver("candidate"),
        runtime_resolver=lambda _input: runtime,
        workspace_manager=CliWorkspaceManager(tmp_path),
    )

    async def exercise():
        return [event async for event in adapter.start(_run_input())]

    events = asyncio.run(exercise())

    assert [event.sequence for event in events] == list(range(1, len(events) + 1))
    assert AgentEventKind.TEXT_DELTA in [event.kind for event in events]
    assert sum(event.kind is AgentEventKind.TOOL_STARTED for event in events) == 2
    assert sum(event.kind is AgentEventKind.TOOL_COMPLETED for event in events) == 2
    assert sum(event.kind is AgentEventKind.CANDIDATE_CREATED for event in events) == 1
    assert events[-1].kind is AgentEventKind.RUN_FINISHED
    assert events[-1].payload["outcome"] == "candidate_ready"
    assert runtime.finished is not None


def test_pi_adapter_cancel_revokes_token_and_reaps_process(
    sample_analysis: dict,
    tmp_path: Path,
) -> None:
    adapter = PiAgentAdapter(
        launch_resolver=_resolver("slow"),
        runtime_resolver=lambda _input: _runtime(sample_analysis),
        workspace_manager=CliWorkspaceManager(tmp_path),
        cancel_grace_seconds=0.2,
    )

    async def exercise():
        stream = adapter.start(_run_input())
        await anext(stream)
        await anext(stream)
        pending = asyncio.create_task(anext(stream))
        await adapter.cancel("run-pi")
        return await asyncio.wait_for(pending, timeout=1)

    terminal = asyncio.run(exercise())

    assert terminal.kind is AgentEventKind.RUN_FINISHED
    assert terminal.payload["outcome"] == "cancelled"
    assert adapter.active_process_count == 0


def test_pi_adapter_sanitizes_malformed_output(
    sample_analysis: dict,
    tmp_path: Path,
) -> None:
    adapter = PiAgentAdapter(
        launch_resolver=_resolver("broken"),
        runtime_resolver=lambda _input: _runtime(sample_analysis),
        workspace_manager=CliWorkspaceManager(tmp_path),
    )

    async def exercise():
        return [event async for event in adapter.start(_run_input())]

    events = asyncio.run(exercise())

    assert events[-1].kind is AgentEventKind.RUN_FAILED
    assert events[-1].payload == {
        "code": "cli_protocol_failed",
        "message": "Pi CLI 返回了无效事件",
    }
