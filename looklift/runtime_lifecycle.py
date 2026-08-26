"""声明式 Runtime 共用的启动、事件校验、取消和回收引擎。"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Mapping

from .agent_adapter import AgentAdapter, AgentEvent, AgentRunInput
from .runtime_registry import RuntimeRegistry


class RuntimeLifecycleError(RuntimeError):
    """Runtime 生命周期失败，错误正文已经脱敏。"""


class RuntimeCapabilityError(RuntimeLifecycleError):
    """所选 Runtime 不满足本次 Attempt 的明确能力要求。"""


AdapterFactory = Callable[[], AgentAdapter]


class RuntimeLifecycleEngine:
    """只运行用户指定 Runtime，不实现跨 Provider 自动回退。"""

    def __init__(
        self,
        registry: RuntimeRegistry,
        *,
        factories: Mapping[str, AdapterFactory],
    ) -> None:
        self._registry = registry
        self._factories = dict(factories)
        self._active: dict[str, AgentAdapter] = {}

    @property
    def active_run_ids(self) -> tuple[str, ...]:
        return tuple(self._active)

    async def start(
        self,
        runtime_id: str,
        run_input: AgentRunInput,
        *,
        required_capabilities: set[str] | frozenset[str] = frozenset(),
        timeout_seconds: float | None = None,
    ) -> AsyncIterator[AgentEvent]:
        definition = self._registry.get(runtime_id)
        missing = set(required_capabilities) - set(definition.permission_profile)
        if missing:
            raise RuntimeCapabilityError(
                f"Runtime 缺少能力：{', '.join(sorted(missing))}"
            )
        if run_input.run_id in self._active:
            raise RuntimeLifecycleError("Run 已有活动 Runtime")
        factory = self._factories.get(runtime_id)
        if factory is None:
            raise RuntimeLifecycleError("Runtime 未配置 Adapter Factory")
        try:
            adapter = factory()
        except Exception as exc:
            raise RuntimeLifecycleError("Runtime Adapter 创建失败") from exc

        self._active[run_input.run_id] = adapter
        expected_sequence = 1
        terminal_seen = False
        try:
            async with asyncio.timeout(timeout_seconds):
                async for event in adapter.start(run_input):
                    if (
                        event.run_id != run_input.run_id
                        or event.attempt_id != run_input.attempt_id
                        or event.sequence != expected_sequence
                    ):
                        raise RuntimeLifecycleError("Runtime 事件身份或序号不合法")
                    expected_sequence += 1
                    terminal_seen = event.kind.terminal
                    payload = dict(event.payload)
                    payload["runtime"] = {
                        "runtime_id": runtime_id,
                        "capabilities": sorted(definition.capabilities),
                        "supports_resume": definition.supports_resume,
                    }
                    yield AgentEvent(
                        kind=event.kind,
                        run_id=event.run_id,
                        attempt_id=event.attempt_id,
                        sequence=event.sequence,
                        payload=payload,
                    )
                if not terminal_seen:
                    raise RuntimeLifecycleError("Runtime 未产生终态事件")
        except TimeoutError as exc:
            raise RuntimeLifecycleError("Runtime 执行超时") from exc
        except RuntimeLifecycleError:
            raise
        except Exception as exc:
            raise RuntimeLifecycleError("Runtime 执行失败") from exc
        finally:
            if not terminal_seen:
                await adapter.cancel(run_input.run_id)
            await adapter.dispose(run_input.run_id)
            self._active.pop(run_input.run_id, None)

    async def cancel(self, run_id: str) -> None:
        adapter = self._active.get(run_id)
        if adapter is not None:
            await adapter.cancel(run_id)

    async def dispose(self, run_id: str) -> None:
        adapter = self._active.pop(run_id, None)
        if adapter is not None:
            await adapter.dispose(run_id)
