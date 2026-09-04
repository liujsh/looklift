"""Daemon 侧 Agent Attempt 的 SSE stream/cancel 出口（spec 8.2）。

线程模型：本机 `ThreadingHTTPServer` 每个请求一个线程。stream 路由在请求线程里
用 `asyncio.run` 驱动 `RuntimeLifecycleEngine` 的异步事件迭代器，把统一 Harness
事件逐帧写出 `text/event-stream`；cancel 路由通过线程安全的取消令牌
（`threading.Event`，同一 manager 的取消令牌）通知 stream 线程停止。

Adapter 工厂按 `runtime_id` 注册，测试可注入 fake factory；真实 `openai-api`
工厂经 `register_openai_adapter_factory` 接入（8.1 的 `make_openai_adapter_factory`
装配候选 Runtime、快照/凭据解析器与传输）。终态唯一性由
`RuntimeLifecycleEngine` 保证；本模块只负责在流意外中止（取消 / 异常 /
未产生终态）时补发一个失败终态帧，避免客户端只看到连接关闭而没有终态。
"""
from __future__ import annotations

import asyncio
import base64
import json
import threading
from collections.abc import Callable, Mapping
from typing import Any

from ..agent_adapter import (
    AgentAdapter,
    AgentEvent,
    AgentEventKind,
    AgentImage,
    AgentRunInput,
)
from ..builtin_runtimes import builtin_runtime_registry
from ..domain_pack import compile_domain_pack
from ..domain_pack_types import DomainPackRequest, VersionedJson, VersionedText
from ..harness_events import encode_sse
from ..runtime_lifecycle import RuntimeLifecycleEngine
from ..runtime_registry import RuntimeRegistry

AdapterFactory = Callable[[], AgentAdapter]

# runtime_id -> AdapterFactory；测试用 register_runtime_factory 注入 fake。
_FACTORIES: dict[str, AdapterFactory] = {}
_FACTORY_LOCK = threading.Lock()

# run_id -> 取消令牌；stream 线程轮询，cancel 线程 set。
_CANCEL: dict[str, threading.Event] = {}
_CANCEL_LOCK = threading.Lock()


def register_runtime_factory(runtime_id: str, factory: AdapterFactory) -> None:
    """注册一次 Attempt 的 Adapter 工厂；测试/集成注入 fake 或真实 Harness。"""
    if not runtime_id or not factory:
        raise ValueError("Runtime ID 与 Adapter Factory 不能为空")
    with _FACTORY_LOCK:
        _FACTORIES[runtime_id] = factory


def register_openai_adapter_factory(factory: AdapterFactory) -> None:
    """把真实 `openai-api` Adapter 工厂注册进 Factory 表（spec 8.1 接线）。"""
    register_runtime_factory("openai-api", factory)


def clear_runtime_factories() -> None:
    """清空工厂表（测试隔离用）。"""
    with _FACTORY_LOCK:
        _FACTORIES.clear()


def _runtime_engine() -> RuntimeLifecycleEngine:
    registry: RuntimeRegistry = builtin_runtime_registry()
    with _FACTORY_LOCK:
        factories = dict(_FACTORIES)
    return RuntimeLifecycleEngine(registry, factories=factories)


def request_cancel(run_id: str) -> None:
    """cancel 路由调用：设置同一 manager 的取消令牌。"""
    _cancel_event(run_id).set()


def _cancel_event(run_id: str) -> threading.Event:
    with _CANCEL_LOCK:
        return _CANCEL.setdefault(run_id, threading.Event())


def _clear_cancel(run_id: str) -> None:
    with _CANCEL_LOCK:
        _CANCEL.pop(run_id, None)


def build_run_input(payload: Mapping[str, Any]) -> AgentRunInput:
    """从请求体装配冻结的 `AgentRunInput`（不保存 API Key / 原图）。"""
    try:
        run_id = str(payload["run_id"])
        attempt_id = str(payload["attempt_id"])
        model = str(payload["model"])
        instructions = str(payload["domain_pack"]["instructions"])
        user_message = str(payload["domain_pack"]["user_message"])
        proxy_jpeg = base64.b64decode(str(payload["proxy_jpeg"]), validate=False)
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Attempt 输入缺少必要字段") from exc
    if not proxy_jpeg:
        raise ValueError("proxy_jpeg 不能为空")
    pack = compile_domain_pack(
        DomainPackRequest(
            system_contract=VersionedText("system", 1, "禁止正式提交。"),
            domain_contract=VersionedText("domain", 1, instructions),
            tool_contract=VersionedJson(
                "tools",
                1,
                {"tools": ["render_candidate", "finish_candidate"]},
            ),
            user_goal=user_message,
            run_context={"transport": "daemon-sse"},
        )
    )
    return AgentRunInput(run_id, attempt_id, pack, AgentImage("image/jpeg", proxy_jpeg), model)


def _terminal_failed(
    run_input: AgentRunInput, sequence: int, code: str, message: str
) -> AgentEvent:
    return AgentEvent(
        kind=AgentEventKind.RUN_FAILED,
        run_id=run_input.run_id,
        attempt_id=run_input.attempt_id,
        sequence=sequence,
        payload={"code": code, "message": message},
    )


def make_streamer(
    runtime_id: str, run_input: AgentRunInput
) -> Callable[[Callable[[bytes], None]], None]:
    """返回 `(write: Callable[[bytes], None]) -> None` 的流式执行器。"""

    def stream(write: Callable[[bytes], None]) -> None:
        asyncio.run(_emit(runtime_id, run_input, write))

    return stream


async def _emit(
    runtime_id: str,
    run_input: AgentRunInput,
    write: Callable[[bytes], None],
) -> None:
    """在请求线程内消费一次 Attempt 事件并逐帧写出，保证唯一终态。

    cancel 令牌是线程安全的 `threading.Event`，与 asyncio 事件循环无关；因此
    消费被放进独立 task，主协程轮询令牌，令牌置位时取消该 task（能打断阻塞在
    await 上的 Adapter），从而对任何 Adapter 都能及时响应取消。
    """
    engine = _runtime_engine()
    token = _cancel_event(run_input.run_id)
    terminal_sent = False
    last_sequence = 0

    async def _consume() -> None:
        nonlocal terminal_sent, last_sequence
        async for event in engine.start(runtime_id, run_input):
            write(encode_sse(event))
            last_sequence = event.sequence
            if event.kind.terminal:
                terminal_sent = True

    task = asyncio.create_task(_consume())
    try:
        while not task.done():
            if token.is_set():
                task.cancel()
                break
            await asyncio.sleep(0.02)
        await task
    except asyncio.CancelledError:
        pass  # 取消：终止消费，下面统一补发取消终态
    except Exception:
        pass  # 运行时异常：补发失败终态，不向客户端 500
    finally:
        if not task.done():
            task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        if not terminal_sent:
            cancelled = token.is_set()
            write(
                encode_sse(
                    _terminal_failed(
                        run_input,
                        last_sequence + 1,
                        "cancelled" if cancelled else "runtime_failed",
                        "Attempt 已取消" if cancelled else "运行时未产生合法终态",
                    )
                )
            )
        _clear_cancel(run_input.run_id)
