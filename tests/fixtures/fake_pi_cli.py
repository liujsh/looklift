"""测试专用 Pi JSON 事件进程，经真实 localhost Gateway 调用工具。"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.request
from pathlib import Path


def _send(value: dict) -> None:
    print(json.dumps(value, ensure_ascii=False), flush=True)


def _call(name: str, arguments: dict) -> dict:
    request = urllib.request.Request(
        f"{os.environ['LOOKLIFT_GATEWAY_URL']}/tools/{name}",
        data=json.dumps(arguments).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {os.environ['LOOKLIFT_TOOL_TOKEN']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=2) as response:
        return json.loads(response.read())["result"]


def _tool_start(name: str, call_id: str, arguments: dict) -> None:
    _send(
        {
            "type": "tool_execution_start",
            "toolCallId": call_id,
            "toolName": name,
            "args": arguments,
        }
    )


def _tool_end(name: str, call_id: str, result: dict) -> None:
    _send(
        {
            "type": "tool_execution_end",
            "toolCallId": call_id,
            "toolName": name,
            "result": {"details": result},
            "isError": False,
        }
    )


def main() -> None:
    mode = sys.argv[1]
    if mode == "slow":
        _send({"type": "agent_start"})
        _send(
            {
                "type": "message_update",
                "assistantMessageEvent": {"type": "text_delta", "delta": "等待取消"},
            }
        )
        time.sleep(60)
        return
    if mode == "broken":
        print("private malformed payload", flush=True)
        return

    workspace = Path.cwd()
    assert (workspace / "DOMAIN_PACK.md").is_file()
    assert (workspace / "proxy.jpg").read_bytes().startswith(b"\xff\xd8")
    _send({"type": "session", "version": 3, "id": "fake", "cwd": "redacted"})
    _send({"type": "agent_start"})
    _send(
        {
            "type": "message_update",
            "assistantMessageEvent": {"type": "text_delta", "delta": "开始修图"},
        }
    )
    render_arguments = {
        "operations": [
            {
                "type": "scalar",
                "path": "basic.exposure",
                "mode": "delta",
                "value": 0.2,
                "reason": "Fake Pi 测试",
            }
        ],
        "intent": "生成候选",
        "template_strength": None,
    }
    _tool_start("render_candidate", "render-pi", render_arguments)
    rendered = _call("render_candidate", render_arguments)
    _tool_end("render_candidate", "render-pi", rendered)

    finish_arguments = {
        "outcome": "candidate_ready",
        "candidate_id": rendered["candidate_id"],
        "summary": "Pi 候选完成",
        "review_items": [],
        "uncertainties": [],
        "limitations": [],
    }
    _tool_start("finish_candidate", "finish-pi", finish_arguments)
    finished = _call("finish_candidate", finish_arguments)
    _tool_end("finish_candidate", "finish-pi", finished)
    _send({"type": "agent_end", "messages": []})


if __name__ == "__main__":
    main()
