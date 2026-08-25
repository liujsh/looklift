"""测试专用 JSONL CLI；模拟原生 Harness 发出文本和工具调用。"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def _send(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def _receive() -> dict:
    return json.loads(sys.stdin.readline())


def main() -> None:
    mode = sys.argv[1]
    workspace = Path.cwd()
    if mode == "slow":
        _send({"type": "text_delta", "text": "等待取消"})
        time.sleep(60)
        return
    if mode == "broken":
        print("not-json", flush=True)
        return

    domain = (workspace / "DOMAIN_PACK.md").read_text(encoding="utf-8")
    proxy = (workspace / "proxy.jpg").read_bytes()
    leaked = any(
        name in os.environ
        for name in ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "LOOKLIFT_SECRET")
    )
    workspace_ok = "自然提亮当前照片" in domain and proxy.startswith(bytes((255, 216)))
    _send(
        {
            "type": "text_delta",
            "text": (
                f"workspace-ok:{workspace_ok}:{leaked}"
            ),
        }
    )
    _send(
        {
            "type": "tool_call",
            "id": "render-1",
            "name": "render_candidate",
            "arguments": {
                "operations": [
                    {
                        "type": "scalar",
                        "path": "basic.exposure",
                        "mode": "delta",
                        "value": 0.2,
                        "reason": "Fake CLI 测试",
                    }
                ],
                "intent": "生成候选",
                "template_strength": None,
            },
        }
    )
    rendered = _receive()
    result = rendered["result"]
    preview = workspace / rendered["content"]["preview_file"]
    assert result["ok"] is True and preview.read_bytes().startswith(b"\xff\xd8")

    _send(
        {
            "type": "tool_call",
            "id": "finish-1",
            "name": "finish_candidate",
            "arguments": {
                "outcome": "candidate_ready",
                "candidate_id": result["candidate_id"],
                "summary": "候选可供复核",
                "review_items": [],
                "uncertainties": [],
                "limitations": [],
            },
        }
    )
    finished = _receive()
    assert finished["result"]["ok"] is True


if __name__ == "__main__":
    main()
