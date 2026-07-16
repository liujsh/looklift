import json
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
