from __future__ import annotations

import httpx

from looklift.provider_detection import detect_provider
from looklift.provider_snapshot import ProviderProtocol, ProviderSnapshot


def test_provider_detection_uses_no_proxy_and_returns_models() -> None:
    snapshot = ProviderSnapshot(
        "openai",
        "https://api.openai.com/v1",
        "gpt-5",
        "credential://openai/default",
        ProviderProtocol.OPENAI_CHAT_COMPLETIONS,
        4096,
        1,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer sk-test"
        return httpx.Response(200, json={"data": [{"id": "gpt-5"}]})

    result = detect_provider(
        snapshot,
        api_key="sk-test",
        resolver=lambda _host: ("93.184.216.34",),
        transport=httpx.MockTransport(handler),
    )

    assert result.available is True
    assert result.models == ("gpt-5",)


def test_provider_detection_rejects_redirect() -> None:
    snapshot = ProviderSnapshot(
        "openai",
        "https://api.openai.com/v1",
        "gpt-5",
        "credential://openai/default",
        ProviderProtocol.OPENAI_CHAT_COMPLETIONS,
        4096,
        1,
    )
    result = detect_provider(
        snapshot,
        api_key="sk-test",
        resolver=lambda _host: ("93.184.216.34",),
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(302, headers={"location": "https://evil.example"})
        ),
    )
    assert result.available is False
    assert result.error_code == "redirect_rejected"
