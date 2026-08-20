"""Fake CLI 与未来 CLI Driver 共用的内部 JSONL 进程协议。"""

from __future__ import annotations

import asyncio
import json
from typing import Any


_MAX_EVENT_BYTES = 256 * 1024


async def read_cli_event(
    process: asyncio.subprocess.Process,
) -> dict[str, Any] | None:
    if process.stdout is None:
        raise RuntimeError("CLI stdout 未连接")
    line = await process.stdout.readline()
    if not line:
        return None
    if len(line) > _MAX_EVENT_BYTES:
        raise ValueError("CLI 事件过大")
    value = json.loads(line)
    if not isinstance(value, dict):
        raise ValueError("CLI 事件必须是对象")
    return value


def parse_tool_call(source: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    name = source.get("name")
    call_id = source.get("id")
    arguments = source.get("arguments")
    if not isinstance(name, str) or not isinstance(call_id, str):
        raise ValueError("工具身份无效")
    if not isinstance(arguments, dict):
        raise ValueError("工具参数无效")
    return name, call_id, arguments


async def send_tool_result(
    process: asyncio.subprocess.Process,
    call_id: str,
    result: dict[str, Any],
    content: dict[str, Any] | None,
) -> None:
    if process.stdin is None:
        raise RuntimeError("CLI stdin 未连接")
    response: dict[str, Any] = {"type": "tool_result", "id": call_id, "result": result}
    if content is not None:
        response["content"] = content
    process.stdin.write(
        json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        + b"\n"
    )
    await process.stdin.drain()
