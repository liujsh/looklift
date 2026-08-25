"""Fake/Driver JSONL 子进程到统一 Agent Adapter ABI 的契约桥。"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .agent_adapter import AgentEvent, AgentEventKind, AgentRunInput
from .candidate_runtime import CandidateRuntime
from .cli_workspace import (
    CliWorkspace,
    CliWorkspaceManager,
    sanitized_cli_environment,
)
from .cli_jsonl_protocol import parse_tool_call, read_cli_event, send_tool_result
from .cli_process import reap_cli_process
from .scoped_tool_gateway import ScopedToolGateway


CommandResolver = Callable[[AgentRunInput], Sequence[str]]
RuntimeResolver = Callable[[AgentRunInput], CandidateRuntime]


@dataclass
class _ActiveCli:
    process: asyncio.subprocess.Process
    runtime: CandidateRuntime
    workspace: CliWorkspace
    token: str
    cancelled: bool = False


class JsonlCliAgentAdapter:
    """测试 CLI Driver 契约；真实 CLI 使用各自原生事件 Adapter。"""

    def __init__(
        self,
        *,
        command_resolver: CommandResolver,
        runtime_resolver: RuntimeResolver,
        workspace_manager: CliWorkspaceManager,
        tool_gateway: ScopedToolGateway | None = None,
        cancel_grace_seconds: float = 0.5,
    ) -> None:
        self._command_resolver = command_resolver
        self._runtime_resolver = runtime_resolver
        self._workspace_manager = workspace_manager
        self._tool_gateway = tool_gateway or ScopedToolGateway()
        self._cancel_grace_seconds = cancel_grace_seconds
        self._active: dict[str, _ActiveCli] = {}
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
        try:
            runtime = self._runtime_resolver(run_input)
            _validate_binding(run_input, runtime)
            command = tuple(self._command_resolver(run_input))
            if not command or any(not isinstance(item, str) or not item for item in command):
                raise ValueError("CLI 命令无效")
            workspace = self._workspace_manager.create(run_input)
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=workspace.path,
                env=sanitized_cli_environment(os.environ),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
        except Exception:
            if workspace is not None:
                self._workspace_manager.dispose(workspace)
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "cli_start_failed", "message": "本地 CLI 启动失败"},
            )
            return

        attempt_key = (run_input.run_id, run_input.attempt_id)
        self._attempts.add(attempt_key)
        self._workspaces.setdefault(run_input.run_id, []).append(workspace)
        grant = self._tool_gateway.bind(runtime)
        active = _ActiveCli(
            process=process,
            runtime=runtime,
            workspace=workspace,
            token=grant.token,
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
                            {"code": "cli_interrupted", "message": "本地 CLI 提前退出"},
                        )
                    terminal = True
                    break
                if source.get("type") == "text_delta":
                    text = source.get("text")
                    if not isinstance(text, str):
                        raise ValueError("文本事件无效")
                    yield event(AgentEventKind.TEXT_DELTA, {"text": text})
                    continue
                if source.get("type") != "tool_call":
                    raise ValueError("事件类型无效")

                tool_name, tool_call_id, arguments = parse_tool_call(source)
                yield event(
                    AgentEventKind.TOOL_STARTED,
                    {"tool_name": tool_name, "tool_call_id": tool_call_id},
                )
                result, content = _dispatch_tool(
                    active,
                    self._workspace_manager,
                    self._tool_gateway,
                    tool_name,
                    arguments,
                )
                await send_tool_result(process, tool_call_id, result, content)
                yield event(
                    AgentEventKind.TOOL_COMPLETED,
                    {
                        "tool_name": tool_name,
                        "tool_call_id": tool_call_id,
                        "ok": result.get("ok") is True,
                    },
                )
                if tool_name == "render_candidate" and result.get("ok") is True:
                    yield event(
                        AgentEventKind.CANDIDATE_CREATED,
                        {
                            "candidate_id": result["candidate_id"],
                            "parent_candidate_id": result.get("parent_candidate_id"),
                            "remaining_render_calls": result["remaining_render_calls"],
                        },
                    )
                if tool_name == "finish_candidate" and result.get("ok") is True:
                    yield event(
                        AgentEventKind.RUN_FINISHED,
                        {key: value for key, value in result.items() if value is not None},
                    )
                    terminal = True
                    break
        except ValueError:
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "cli_protocol_failed", "message": "本地 CLI 返回了无效事件"},
            )
            terminal = True
        except Exception:
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "cli_failed", "message": "本地 CLI 执行失败"},
            )
            terminal = True
        finally:
            self._tool_gateway.revoke(active.token)
            await reap_cli_process(process, self._cancel_grace_seconds)
            self._active.pop(run_input.run_id, None)

        if not terminal:
            yield event(
                AgentEventKind.RUN_FAILED,
                {"code": "missing_terminal", "message": "本地 CLI 未返回合法终态"},
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


def _dispatch_tool(
    active: _ActiveCli,
    manager: CliWorkspaceManager,
    gateway: ScopedToolGateway,
    name: str,
    arguments: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    result = gateway.call(active.token, name, arguments)
    payload = dict(result.payload)
    if result.preview_jpeg is not None:
        relative = manager.write_candidate(active.workspace, result.preview_jpeg)
        return payload, {"preview_file": relative}
    return payload, None


def _validate_binding(run_input: AgentRunInput, runtime: CandidateRuntime) -> None:
    if (
        runtime.binding.run_id != run_input.run_id
        or runtime.binding.attempt_id != run_input.attempt_id
    ):
        raise ValueError("Runtime 身份与 CLI 输入不一致")
