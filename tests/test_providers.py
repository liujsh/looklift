import json
import sys
import types
from pathlib import Path

import pytest

from looklift import provider_http
from looklift import providers


def test_cli_provider_builds_read_instructions(monkeypatch):
    """image block 应转成 Read 工具指令;text block 原样;schema 拼在结尾。"""
    captured = {}

    def fake_run(cmd, input, **kw):
        captured["prompt"] = input

        class P:
            returncode = 0
            stdout = json.dumps({"result": json.dumps({"summary": "ok"})})
            stderr = ""

        return P()

    monkeypatch.setattr(providers.subprocess, "run", fake_run)
    monkeypatch.setattr(providers.shutil, "which", lambda _: "claude")
    p = providers.ClaudeCliProvider()
    out = p.complete(
        "SYS",
        [
            {"type": "text", "text": "任务说明"},
            {"type": "image", "path": Path("a.jpg"), "label": "成片"},
        ],
        {"type": "object"},
    )
    assert out == {"summary": "ok"}
    assert "SYS" in captured["prompt"]
    assert "任务说明" in captured["prompt"]
    assert "Read 工具" in captured["prompt"] and "a.jpg" in captured["prompt"]
    assert "JSON Schema" in captured["prompt"]


def test_get_provider_auto(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-x")
    assert isinstance(providers.get_provider("auto"), providers.AnthropicProvider)
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    monkeypatch.setattr(providers.shutil, "which", lambda _: "claude")
    assert isinstance(providers.get_provider("auto"), providers.ClaudeCliProvider)


def test_get_provider_none_available(monkeypatch, tmp_path):
    from looklift import config
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "none.toml")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(providers.shutil, "which", lambda _: None)
    with pytest.raises(RuntimeError):
        providers.get_provider("auto")


def test_get_provider_auto_uses_config_api_key(monkeypatch, tmp_path):
    """未设置 ANTHROPIC_API_KEY,但 config.toml 里配了 api_key → 也应选中 api 后端。"""
    from looklift import config
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text('api_key = "sk-cfg"\n', encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert isinstance(providers.get_provider("auto"), providers.AnthropicProvider)


def _install_fake_anthropic(monkeypatch, captured):
    """把 anthropic 模块整个替换成假的,断言不联网。"""

    class FakeMessage:
        stop_reason = "end_turn"
        content = [types.SimpleNamespace(type="text", text=json.dumps({"summary": "ok"}))]

    class FakeStream:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_final_message(self):
            return FakeMessage()

    class FakeMessages:
        def stream(self, **kw):
            captured["stream_kwargs"] = kw
            return FakeStream()

    class FakeClient:
        def __init__(self, **kw):
            captured["client_kwargs"] = kw
            self.messages = FakeMessages()

    fake_anthropic = types.SimpleNamespace(Anthropic=FakeClient)
    monkeypatch.setitem(sys.modules, "anthropic", fake_anthropic)


def test_api_provider_wires_config_key_baseurl_and_model(monkeypatch, tmp_path):
    """AnthropicProvider 应把 config.toml 的 api_key/base_url 传给 Anthropic() 构造函数,
    并用 config 的 model 覆盖默认值;image block 需带上 label 文字并转成图片 block。"""
    from looklift import config
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        'api_key = "sk-cfg"\nbase_url = "https://proxy.example"\nmodel = "claude-custom"\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_path)

    captured: dict = {}
    _install_fake_anthropic(monkeypatch, captured)

    from PIL import Image
    img_path = tmp_path / "a.jpg"
    Image.new("RGB", (4, 4), (128, 128, 128)).save(img_path)

    p = providers.AnthropicProvider()
    out = p.complete(
        "SYS",
        [
            {"type": "text", "text": "任务说明"},
            {"type": "image", "path": img_path, "label": "成片"},
        ],
        {"type": "object"},
    )

    assert out == {"summary": "ok"}
    assert captured["client_kwargs"] == {"api_key": "sk-cfg", "base_url": "https://proxy.example"}
    assert captured["stream_kwargs"]["model"] == "claude-custom"
    content = captured["stream_kwargs"]["messages"][0]["content"]
    assert content[0] == {"type": "text", "text": "任务说明"}
    assert content[1] == {"type": "text", "text": "这是成片:"}
    assert content[2]["type"] == "image"


def test_api_provider_no_config_key_falls_back_to_sdk_default(monkeypatch, tmp_path):
    """config 未配置 api_key/base_url 时传 None,交给 SDK 走环境变量(不改变既有行为)。"""
    from looklift import config
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "none.toml")

    captured: dict = {}
    _install_fake_anthropic(monkeypatch, captured)

    p = providers.AnthropicProvider()
    p.complete("SYS", [{"type": "text", "text": "hi"}], {"type": "object"})

    assert captured["client_kwargs"] == {"api_key": None, "base_url": None}


def test_openai_compat_wires_vision_request_and_extracts_json(monkeypatch, tmp_path):
    from PIL import Image

    image_path = tmp_path / "a.png"
    Image.new("RGB", (4, 4), (10, 20, 30)).save(image_path)
    captured = {}

    def fake_post(url, payload, *, headers, timeout):
        captured.update(url=url, payload=payload, headers=headers, timeout=timeout)
        return {"choices": [{"message": {"content": '```json\n{"summary":"ok"}\n```'}}]}

    monkeypatch.setattr(provider_http, "post_json", fake_post)
    provider = providers.OpenAICompatProvider(
        "https://proxy.example/v1/", "sk-test", "vision-model", timeout=17
    )
    result = provider.complete(
        "SYS",
        [
            {"type": "text", "text": "任务"},
            {"type": "image", "path": image_path, "label": "成片"},
        ],
        {"type": "object"},
    )

    assert result == {"summary": "ok"}
    assert captured["url"] == "https://proxy.example/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer sk-test"
    assert captured["timeout"] == 17
    assert captured["payload"]["model"] == "vision-model"
    assert captured["payload"]["max_tokens"] == 16000
    assert captured["payload"]["messages"][0] == {"role": "system", "content": "SYS"}
    content = captured["payload"]["messages"][1]["content"]
    assert content[0] == {"type": "text", "text": "任务"}
    assert content[1] == {"type": "text", "text": "这是成片:"}
    assert content[2]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "JSON Schema" in content[-1]["text"]


@pytest.mark.parametrize(
    ("status", "message"),
    [(401, "api_key"), (404, "模型.*base_url"), (429, "请求被拒绝")],
)
def test_openai_compat_maps_http_errors_to_chinese(monkeypatch, status, message):
    def fail(*args, **kwargs):
        raise provider_http.HTTPStatusError(status, "bad")

    monkeypatch.setattr(provider_http, "post_json", fail)
    provider = providers.OpenAICompatProvider("https://proxy.example/v1", "bad", "model")
    with pytest.raises(RuntimeError, match=message):
        provider.complete("SYS", [{"type": "text", "text": "任务"}], {})


def test_openai_compat_maps_connection_error(monkeypatch):
    def fail(*args, **kwargs):
        raise provider_http.HTTPConnectionError("refused")

    monkeypatch.setattr(provider_http, "post_json", fail)
    provider = providers.OpenAICompatProvider("https://proxy.example/v1", "key", "model")
    with pytest.raises(RuntimeError, match="连接失败.*base_url"):
        provider.complete("SYS", [{"type": "text", "text": "任务"}], {})


def test_get_provider_builds_openai_compat_from_config(monkeypatch, tmp_path):
    from looklift import config

    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(
        'provider = "openai_compat"\nbase_url = "https://proxy.example/v1"\n'
        'api_key = "sk-cfg"\nmodel = "vision"\ntimeout = 33\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_path)

    provider = providers.get_provider("auto")
    assert isinstance(provider, providers.OpenAICompatProvider)
    assert provider.base_url == "https://proxy.example/v1"
    assert provider.api_key == "sk-cfg"
    assert provider.model == "vision"
    assert provider.timeout == 33
