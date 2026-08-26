from __future__ import annotations

import asyncio

from looklift.connector_execution import ConnectorExecution


def test_timeout_is_classified_and_late_result_is_ignored() -> None:
    async def scenario():
        async def slow():
            await asyncio.sleep(0.05)
            return "late"

        return await ConnectorExecution().run(slow, timeout_seconds=0.001)

    result = asyncio.run(scenario())
    assert result.status == "timeout"
    assert result.value is None
    assert result.late_result_isolated is True


def test_cancel_isolated_without_implicit_retry() -> None:
    async def scenario():
        cancelled = asyncio.Event()

        async def slow():
            await asyncio.sleep(0.05)
            return "late"

        task = asyncio.create_task(
            ConnectorExecution().run(slow, timeout_seconds=1, cancel_event=cancelled)
        )
        await asyncio.sleep(0)
        cancelled.set()
        return await task

    result = asyncio.run(scenario())
    assert result.status == "cancelled"
    assert result.attempts == 1
    assert result.late_result_isolated is True


def test_retry_is_explicit_and_never_changes_provider() -> None:
    async def scenario():
        calls = 0

        async def flaky():
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("temporary")
            return "ok"

        result = await ConnectorExecution().run(flaky, timeout_seconds=1, retries=1)
        return result, calls

    result, calls = asyncio.run(scenario())
    assert result.status == "succeeded"
    assert result.value == "ok"
    assert result.attempts == 2
    assert calls == 2
