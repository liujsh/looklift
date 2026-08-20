"""Fake CLI 与未来 CLI Driver 共用的内部 JSONL 进程协议。"""

from __future__ import annotations

import asyncio
import json
from typing import Any


CLI_EVENT_STREAM_LIMIT = 8 * 1024 * 1024
_MAX_EVENT_BYTES = CLI_EVENT_STREAM_LIMIT - 1


class CliProtocolError(ValueError):
    """携带不含原始行内容的 JSONL 失败分类。"""

    def __init__(self, category: str) -> None:
        super().__init__("CLI JSONL 协议无效")
        self.category = category


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
    try:
        value = json.loads(line)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CliProtocolError(_classify_non_json(line)) from exc
    if not isinstance(value, dict):
        raise ValueError("CLI 事件必须是对象")
    return value


def _classify_non_json(line: bytes) -> str:
    text = line.decode("utf-8", errors="replace").strip().casefold()
    if text.startswith("loaded extension") or text.startswith("[extension"):
        return "startup_log"
    if text.startswith("warning") or text.startswith("warn"):
        return "warning_log"
    if text.startswith("error") or text.startswith("failed"):
        return "error_log"
    if text.startswith("{") or text.startswith("["):
        return "malformed_json"
    return "non_json"


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
