from looklift.openai_protocol import build_openai_request
from looklift.provider_snapshot import ProviderProtocol, ProviderSnapshot


def _snapshot():
    return ProviderSnapshot(
        "openai", "https://api.openai.com/v1", "model", "credential://openai/default",
        ProviderProtocol.OPENAI_CHAT_COMPLETIONS, 1024, 1,
    )


def test_openai_projection_supports_text_only_and_multiple_plugin_images():
    text_only = build_openai_request(
        _snapshot(), instructions="规则", user_message="写文案", proxy_jpeg=None, tools=()
    )
    assert text_only["messages"][1]["content"] == [{"type": "text", "text": "写文案"}]

    multiple = build_openai_request(
        _snapshot(),
        instructions="规则",
        user_message="比较两张图",
        proxy_jpeg=None,
        proxy_jpegs=(b"one", b"two"),
        tools=(),
    )
    assert [item["type"] for item in multiple["messages"][1]["content"]] == [
        "text", "image_url", "image_url"
    ]
