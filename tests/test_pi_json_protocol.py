"""Pi RPC 初始消息只交付冻结 Domain Pack 与安全代理图。"""

from __future__ import annotations

import base64

from looklift.agent_adapter import AgentImage, AgentRunInput, AgentTaskKind
from looklift.domain_pack_types import CompiledDomainPack
from looklift.pi_json_protocol import pi_prompt_command


def test_pi_prompt_command_contains_domain_goal_and_proxy_without_run_identity() -> None:
    run_input = AgentRunInput(
        run_id="private-run",
        attempt_id="private-attempt",
        domain_pack=CompiledDomainPack(
            instructions="只允许候选工具。",
            user_message="保守提亮照片。",
            source_hashes=(),
            omitted_sources=(),
            content_hash="d" * 64,
            estimated_tokens=12,
        ),
        proxy_image=AgentImage("image/jpeg", b"safe-jpeg"),
        model="provider/model",
    )

    command = pi_prompt_command(run_input)

    assert command["type"] == "prompt"
    assert "只允许候选工具" in command["message"]
    assert "保守提亮照片" in command["message"]
    assert "private-run" not in command["message"]
    assert "private-attempt" not in command["message"]
    assert command["images"] == [
        {
            "type": "image",
            "data": base64.b64encode(b"safe-jpeg").decode("ascii"),
            "mimeType": "image/jpeg",
        }
    ]


def test_pi_plugin_prompt_supports_zero_or_multiple_images_without_candidate_terminal():
    run_input = AgentRunInput(
        "plugin-run",
        "plugin-attempt",
        CompiledDomainPack("插件规则", "准备文案", (), (), "e" * 64, 8),
        AgentImage("image/jpeg", b"one"),
        "provider/model",
        task_kind=AgentTaskKind.PLUGIN_TASK,
        additional_proxy_images=(AgentImage("image/jpeg", b"two"),),
    )
    command = pi_prompt_command(run_input)
    assert len(command["images"]) == 2
    assert "finish_candidate" not in command["message"]

    text_only = AgentRunInput(
        "plugin-run-2", "plugin-attempt-2", run_input.domain_pack, None, "provider/model",
        task_kind=AgentTaskKind.PLUGIN_TASK,
    )
    assert pi_prompt_command(text_only)["images"] == []
