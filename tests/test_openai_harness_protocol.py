from __future__ import annotations

import pytest

from looklift.openai_protocol import OpenAiSseParser, build_openai_request
from looklift.provider_security import (
    ProviderSecurityError,
    ensure_response_size,
    validate_provider_url,
)
from looklift.provider_snapshot import ProviderProtocol, ProviderSnapshot


def _snapshot(*, ollama: bool = False) -> ProviderSnapshot:
    return ProviderSnapshot(
        provider_id="ollama" if ollama else "openai",
        base_url="http://127.0.0.1:11434/v1" if ollama else "https://api.openai.com/v1",
        model="qwen3-vl" if ollama else "gpt-5",
        api_key_ref=None if ollama else "credential://openai/default",
        protocol=(
            ProviderProtocol.OLLAMA_OPENAI_COMPATIBLE
            if ollama
            else ProviderProtocol.OPENAI_CHAT_COMPLETIONS
        ),
        max_tokens=4096,
        config_version=1,
    )


def test_provider_url_rejects_private_remote_and_allows_explicit_ollama() -> None:
    with pytest.raises(ProviderSecurityError, match="禁止网络范围"):
        validate_provider_url(
            "https://provider.example/v1", resolved_ips=("100.64.0.1",)
        )

    validate_provider_url(
        "http://127.0.0.1:11434/v1",
        resolved_ips=("127.0.0.1",),
        local_ollama=True,
    )
    with pytest.raises(ProviderSecurityError, match="大小限制"):
        ensure_response_size(b"1234", limit_bytes=3)


def test_openai_request_contains_proxy_image_tools_and_no_credential() -> None:
    request = build_openai_request(
        _snapshot(),
        instructions="只生成白盒候选",
        user_message="自然提亮",
        proxy_jpeg=b"jpeg",
        tools=({"name": "render_candidate", "inputSchema": {"type": "object"}},),
    )

    assert request["model"] == "gpt-5"
    assert request["stream"] is True
    assert "credential://" not in str(request)
    assert "data:image/jpeg;base64," in str(request)
    assert request["tools"][0]["function"]["name"] == "render_candidate"


def test_sse_parser_normalizes_text_tool_usage_and_terminal() -> None:
    parser = OpenAiSseParser()
    payload = (
        'data: {"choices":[{"delta":{"content":"分析"}}]}\n\n'
        'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"c1","function":{"name":"finish_candidate","arguments":"{\\"outcome\\":\\"no_change_needed\\"}"}}]},"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":2,"completion_tokens":3}}\n\n'
        "data: [DONE]\n\n"
    ).encode()

    events = parser.feed(payload[:40]) + parser.feed(payload[40:]) + parser.finish()

    assert [event.kind for event in events] == ["text", "tool_call", "usage", "done"]
    assert events[1].payload["name"] == "finish_candidate"
