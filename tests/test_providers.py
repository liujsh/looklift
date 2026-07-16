import json
import sys
import types
from pathlib import Path

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
    import pytest
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
