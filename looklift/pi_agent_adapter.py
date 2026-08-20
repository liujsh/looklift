"""Pi 原生 JSON 事件与 Scoped Tool Gateway 的 Agent Adapter。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping
from dataclasses import dataclass
from typing import Any

from .agent_adapter import AgentEvent, AgentEventKind, AgentRunInput
from .candidate_runtime import CandidateRuntime
from .cli_jsonl_protocol import read_cli_event
from .cli_process import reap_cli_process
from .cli_workspace import CliWorkspace, CliWorkspaceManager
from .pi_cli_profile import PiLaunchSpec
from .pi_json_protocol import pi_text_delta, pi_tool_identity, pi_usage_payload
from .scoped_tool_gateway import ScopedToolGateway
from .scoped_tool_http import ScopedToolHttpServer


RuntimeResolver = Callable[[AgentRunInput], CandidateRuntime]
LaunchResolver = Callable[
    [AgentRunInput, CliWorkspace, str, str],
    PiLaunchSpec,
]
@dataclass
class _ActivePi:
    process: asyncio.subprocess.Process
    runtime: CandidateRuntime
    workspace: CliWorkspace
    token: str
    cancelled: bool = False
    latest_candidate_id: str | None = None


class PiAgentAdapter:
    """Pi 负责模型循环；本类只交付上下文、工具和归一事件。"""

    def __init__(
        self,
        *,
        launch_resolver: LaunchResolver,
        runtime_resolver: RuntimeResolver,
        workspace_manager: CliWorkspaceManager,
        tool_gateway: ScopedToolGateway | None = None,
        cancel_grace_seconds: float = 0.5,
    ) -> None:
        self._launch_resolver = launch_resolver
        self._runtime_resolver = runtime_resolver
        self._workspace_manager = workspace_manager
        self._tool_gateway = tool_gateway or ScopedToolGateway()
        self._http = ScopedToolHttpServer(self._tool_gateway)
        self._http_users = 0
        self._cancel_grace_seconds = cancel_grace_seconds
        self._active: dict[str, _ActivePi] = {}
        self._attempts: set[tuple[str, str]] = set()
        self._workspaces: dict[str, list[CliWorkspace]] = {}
        self._disposed: set[str] = set()

    @property
    def active_process_count(self) -> int:
        return len(self._active)

    async def start(self, run_input: AgentRunInput) -> AsyncIterator[AgentEvent]:
        sequence = 0

        def event(kind: AgentEventKind, payload: Mapping[str, Any]) -> AgentEvent:
            nonlocal sequence
            sequence += 1
            return AgentEvent(
                kind=kind,
                run_id=run_input.run_id,
                attempt_id=run_input.attempt_id,
                sequence=sequence,
                payload=payload,
            )

        failure = self._start_failure(run_input)
        if failure is not None:
            yield event(AgentEventKind.RUN_FAILED, failure)
            return

        workspace: CliWorkspace | None = None
        token: str | None = None
        server_acquired = False
        try:
            runtime = self._runtime_resolver(run_input)
            _validate_binding(run_input, runtime)
            workspace = self._workspace_manager.create(run_input)
            grant = self._tool_gateway.bind(runtime)
            token = grant.token
            self._acquire_http()
            server_acquired = True
            launch = self._launch_resolver(
                run_input,
                workspace,
                self._http.url,
                token,
            )
            process = await asyncio.create_subprocess_exec(
                *launch.command,
                cwd=workspace.path,
                env=dict(launch.environment),
                stdin=asyncio.subprocess.DEVNULL,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except Exception:
            if token is not None:
                self._tool_gateway.revoke(token)
            if workspace is not None:
                self._workspace_manager.dispose(workspace)
            if server_acquired:
                self._release_http()
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "cli_start_failed", "message": "Pi CLI 启动失败"},
            )
            return

        attempt_key = (run_input.run_id, run_input.attempt_id)
        self._attempts.add(attempt_key)
        self._workspaces.setdefault(run_input.run_id, []).append(workspace)
        active = _ActivePi(
            process=process,
            runtime=runtime,
            workspace=workspace,
            token=token,
        )
        self._active[run_input.run_id] = active
        yield event(
            AgentEventKind.RUN_STARTED,
            {"model": run_input.model, "domain_pack_hash": run_input.domain_pack.content_hash},
        )

        terminal = False
        try:
            while True:
                source = await read_cli_event(process)
                if source is None:
                    if active.cancelled:
                        yield event(AgentEventKind.RUN_FINISHED, {"outcome": "cancelled"})
                    else:
                        yield event(
                            AgentEventKind.RUN_FAILED,
                            {"code": "cli_interrupted", "message": "Pi CLI 提前退出"},
                        )
                    terminal = True
                    break

                text = pi_text_delta(source)
                if text is not None:
                    yield event(AgentEventKind.TEXT_DELTA, {"text": text})
                usage = pi_usage_payload(source)
                if usage is not None:
                    yield event(AgentEventKind.USAGE_UPDATED, usage)

                source_type = source.get("type")
                if source_type == "tool_execution_start":
                    name, call_id = pi_tool_identity(source)
                    yield event(
                        AgentEventKind.TOOL_STARTED,
                        {"tool_name": name, "tool_call_id": call_id},
                    )
                elif source_type == "tool_execution_end":
                    name, call_id = pi_tool_identity(source)
                    ok = _tool_succeeded(active, name, source)
                    yield event(
                        AgentEventKind.TOOL_COMPLETED,
                        {"tool_name": name, "tool_call_id": call_id, "ok": ok},
                    )
                    if name == "render_candidate" and ok:
                        latest = active.runtime.latest_candidate
                        assert latest is not None
                        active.latest_candidate_id = latest.candidate_id
                        yield event(
                            AgentEventKind.CANDIDATE_CREATED,
                            {
                                "candidate_id": latest.candidate_id,
                                "parent_candidate_id": latest.parent_candidate_id,
                            },
                        )
                    if name == "finish_candidate" and ok:
                        finished = active.runtime.finished
                        assert finished is not None
                        yield event(
                            AgentEventKind.RUN_FINISHED,
                            finished.model_dump(mode="json", exclude_none=True),
                        )
                        terminal = True
                        break
                elif source_type == "agent_end" and active.runtime.finished is None:
                    yield event(
                        AgentEventKind.RUN_FAILED,
                        {"code": "missing_terminal", "message": "Pi CLI 未返回合法终态"},
                    )
                    terminal = True
                    break
        except (ValueError, AssertionError):
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "cli_protocol_failed", "message": "Pi CLI 返回了无效事件"},
            )
            terminal = True
        except Exception:
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "cli_failed", "message": "Pi CLI 执行失败"},
            )
            terminal = True
        finally:
            self._tool_gateway.revoke(active.token)
            await reap_cli_process(process, self._cancel_grace_seconds)
            self._active.pop(run_input.run_id, None)
            self._release_http()

        if not terminal:
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "missing_terminal", "message": "Pi CLI 未返回合法终态"},
            )

    async def cancel(self, run_id: str) -> None:
        active = self._active.get(run_id)
        if active is None:
            return
        active.runtime.cancel()
        self._tool_gateway.revoke(active.token)
        active.cancelled = True
        await reap_cli_process(active.process, self._cancel_grace_seconds)

    async def dispose(self, run_id: str) -> None:
        await self.cancel(run_id)
        for workspace in self._workspaces.pop(run_id, []):
            self._workspace_manager.dispose(workspace)
        self._disposed.add(run_id)

    def _start_failure(self, run_input: AgentRunInput) -> dict[str, str] | None:
        key = (run_input.run_id, run_input.attempt_id)
        if key in self._attempts:
            return {"code": "duplicate_attempt", "message": "同一 Attempt 不能重复启动"}
        if run_input.run_id in self._disposed:
            return {"code": "run_disposed", "message": "本轮已经释放"}
        if run_input.run_id in self._active:
            return {"code": "run_active", "message": "本轮已有正在执行的 Attempt"}
        return None

    def _acquire_http(self) -> None:
        if self._http_users == 0:
            self._http.start()
        self._http_users += 1

    def _release_http(self) -> None:
        self._http_users -= 1
        if self._http_users == 0:
            self._http.close()


def _tool_succeeded(active: _ActivePi, name: str, source: dict[str, Any]) -> bool:
    if source.get("isError") is True:
        return False
    if name == "finish_candidate":
        return active.runtime.finished is not None
    latest = active.runtime.latest_candidate
    return latest is not None and latest.candidate_id != active.latest_candidate_id


def _validate_binding(run_input: AgentRunInput, runtime: CandidateRuntime) -> None:
    if (
        runtime.binding.run_id != run_input.run_id
        or runtime.binding.attempt_id != run_input.attempt_id
    ):
        raise ValueError("Runtime 身份与 Pi 输入不一致")
