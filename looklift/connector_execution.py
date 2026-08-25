"""Connector 调用的超时、取消、晚到隔离和显式重试。"""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Generic, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class ConnectorCallResult(Generic[T]):
    status: str
    value: T | None = None
    error_code: str | None = None
    attempts: int = 0
    late_result_isolated: bool = True


class ConnectorExecution:
    """只执行调用方明确指定的重试，不负责 Provider 降级或切换。"""

    async def run(
        self,
        operation: Callable[[], Awaitable[T]],
        *,
        timeout_seconds: float,
        cancel_event: asyncio.Event | None = None,
        retries: int = 0,
    ) -> ConnectorCallResult[T]:
        if timeout_seconds <= 0 or retries < 0:
            raise ValueError("超时和重试次数必须合法")
        attempts = 0
        while True:
            attempts += 1
            task = asyncio.create_task(operation())
            cancel_task = (
                asyncio.create_task(cancel_event.wait()) if cancel_event is not None else None
            )
            try:
                watched = {task}
                if cancel_task is not None:
                    watched.add(cancel_task)
                done, _ = await asyncio.wait(
                    watched, timeout=timeout_seconds, return_when=asyncio.FIRST_COMPLETED
                )
                if cancel_task is not None and cancel_task in done:
                    self._isolate(task)
                    return ConnectorCallResult(
                        status="cancelled", error_code="cancelled", attempts=attempts
                    )
                if task not in done:
                    self._isolate(task)
                    if attempts <= retries:
                        continue
                    return ConnectorCallResult(
                        status="timeout", error_code="timeout", attempts=attempts
                    )
                try:
                    return ConnectorCallResult(
                        status="succeeded", value=task.result(), attempts=attempts
                    )
                except asyncio.CancelledError:
                    return ConnectorCallResult(
                        status="cancelled", error_code="cancelled", attempts=attempts
                    )
                except Exception as exc:
                    if attempts <= retries:
                        continue
                    return ConnectorCallResult(
                        status="failed", error_code=type(exc).__name__, attempts=attempts
                    )
            finally:
                if cancel_task is not None:
                    cancel_task.cancel()

    @staticmethod
    def _isolate(task: asyncio.Task[object]) -> None:
        """取消并消费晚到任务，禁止其结果回写本次调用。"""
        task.cancel()

        def consume(completed: asyncio.Task[object]) -> None:
            try:
                completed.result()
            except BaseException:
                pass

        task.add_done_callback(consume)
