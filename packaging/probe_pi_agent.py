"""显式运行一次真实 Pi 候选闭环；不会提交或导出正式版本。"""

from __future__ import annotations

import argparse
import asyncio
import json
import tempfile
import time
import uuid
from pathlib import Path

from looklift.agent_adapter import AgentImage, AgentRunInput
from looklift.analyzer import _normalize
from looklift.candidate_rendering import ProxyCandidateRenderer
from looklift.candidate_runtime import CandidateRuntime
from looklift.candidate_runtime_types import InMemoryRunAuthority, RunBinding
from looklift.cli_workspace import CliWorkspaceManager
from looklift.domain_pack import compile_domain_pack
from looklift.domain_pack_sources import load_photo_editing_contract
from looklift.domain_pack_types import DomainPackRequest, VersionedJson, VersionedText
from looklift.pi_agent_adapter import PiAgentAdapter
from looklift.pi_cli_profile import build_pi_launch_resolver, probe_pi
from looklift.scoped_tool_gateway import agent_tool_definitions
from looklift.ai_proxy import prepare_ai_proxy


_SYSTEM_BOUNDARIES = """你是 LookLift 受控修图 Agent。
只能通过 render_candidate 修改白盒参数，通过 finish_candidate 结束。
必须观察工具返回的真实 JPEG 与指标后再判断是否精修；不得声称已保存、导出或提交。
若能力不足，明确限制并结束，不得虚构工具结果。"""


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="本地测试照片")
    parser.add_argument("--model", required=True, help="Pi provider/model")
    parser.add_argument("--executable", default="pi", help="Pi 可执行文件或 .cmd 路径")
    parser.add_argument("--cli-script", type=Path, help="配合 Node 直接启动 Pi cli.js")
    parser.add_argument(
        "--goal",
        default="保守提亮整体并保持自然色彩，避免高光裁切；观察真实候选后决定是否精修。",
    )
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--cancel-after", type=float, help="启动后延迟若干秒取消")
    return parser.parse_args()


def _domain_pack(goal: str):
    return compile_domain_pack(
        DomainPackRequest(
            system_contract=VersionedText(
                "looklift.agent-boundaries",
                1,
                _SYSTEM_BOUNDARIES,
            ),
            domain_contract=load_photo_editing_contract(),
            tool_contract=VersionedJson(
                "looklift.candidate-tools",
                1,
                agent_tool_definitions(),
            ),
            user_goal=goal,
            run_context={"render_budget": 3, "selected_template": None},
        )
    )


async def _run(args: argparse.Namespace) -> int:
    image = args.image.resolve()
    if not image.is_file():
        raise SystemExit(f"照片不存在：{image}")
    executable = (
        (args.executable, str(args.cli_script.resolve()))
        if args.cli_script is not None
        else args.executable
    )
    probe = probe_pi(executable)
    if probe.tier == "unsupported":
        raise SystemExit(probe.reason)

    run_id = f"probe-{uuid.uuid4().hex}"
    attempt_id = f"attempt-{uuid.uuid4().hex}"
    binding = RunBinding(
        run_id=run_id,
        attempt_id=attempt_id,
        lease=f"lease-{uuid.uuid4().hex}",
        base_version_id=f"base-{uuid.uuid4().hex}",
        image_path=image,
        max_render_calls=3,
    )
    authority = InMemoryRunAuthority(binding)
    runtime = CandidateRuntime(
        binding=binding,
        authority=authority,
        baseline_analysis=_normalize({}),
        renderer=ProxyCandidateRenderer(),
    )
    with prepare_ai_proxy(image, include_metadata=False) as proxy:
        run_input = AgentRunInput(
            run_id=run_id,
            attempt_id=attempt_id,
            domain_pack=_domain_pack(args.goal),
            proxy_image=AgentImage("image/jpeg", proxy.path.read_bytes()),
            model=args.model,
        )
        with tempfile.TemporaryDirectory(prefix="looklift-pi-probe-") as directory:
            adapter = PiAgentAdapter(
                launch_resolver=build_pi_launch_resolver(executable=executable),
                runtime_resolver=lambda _run_input: runtime,
                workspace_manager=CliWorkspaceManager(Path(directory)),
            )
            terminal = None
            terminal_payload = None
            cancel_task = None

            async def cancel_later() -> None:
                await asyncio.sleep(args.cancel_after)
                started = time.perf_counter()
                await adapter.cancel(run_id)
                elapsed = time.perf_counter() - started
                print(
                    json.dumps(
                        {"cancel_elapsed_seconds": round(elapsed, 3)},
                        ensure_ascii=False,
                    )
                )

            try:
                async with asyncio.timeout(args.timeout):
                    async for event in adapter.start(run_input):
                        if (
                            event.kind.value == "run_started"
                            and args.cancel_after is not None
                            and cancel_task is None
                        ):
                            cancel_task = asyncio.create_task(cancel_later())
                        payload = dict(event.payload)
                        if event.kind.value == "text_delta":
                            payload = {"text_chars": len(str(payload.get("text", "")))}
                        print(
                            json.dumps(
                                {
                                    "sequence": event.sequence,
                                    "kind": event.kind.value,
                                    "payload": payload,
                                },
                                ensure_ascii=False,
                            )
                        )
                        if event.kind.terminal:
                            terminal = event.kind.value
                            terminal_payload = payload
            except TimeoutError:
                await adapter.cancel(run_id)
                terminal = "timeout"
            finally:
                if cancel_task is not None:
                    if not cancel_task.done():
                        cancel_task.cancel()
                    await asyncio.gather(cancel_task, return_exceptions=True)
                await adapter.dispose(run_id)

    summary = {
        "terminal": terminal,
        "candidate_count": len(runtime.candidates),
        "finished": (
            runtime.finished.model_dump(mode="json", exclude_none=True)
            if runtime.finished is not None
            else None
        ),
        "changes": (
            [change.model_dump(mode="json") for change in runtime.latest_candidate.changes]
            if runtime.latest_candidate is not None
            else []
        ),
        "metrics": (
            runtime.latest_candidate.metrics.model_dump(mode="json")
            if runtime.latest_candidate is not None
            else None
        ),
    }
    print(json.dumps({"probe_summary": summary}, ensure_ascii=False))
    cancelled = (
        terminal == "run_finished"
        and isinstance(terminal_payload, dict)
        and terminal_payload.get("outcome") == "cancelled"
    )
    completed = terminal == "run_finished" and runtime.finished is not None
    return 0 if completed or cancelled else 1


def main() -> int:
    args = _arguments()
    if args.timeout <= 0:
        raise SystemExit("timeout 必须为正数")
    if args.cancel_after is not None and args.cancel_after < 0:
        raise SystemExit("cancel-after 不能为负数")
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
