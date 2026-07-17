import os
from pathlib import Path
import pytest
from looklift import config


def test_load_config_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "nonexistent.toml")
    for k in list(os.environ):
        if k.startswith("LOOKLIFT_"):
            monkeypatch.delenv(k)
    cfg = config.load_config()
    assert cfg["provider"] == "auto"
    assert cfg["api_key"] == ""
    assert cfg["timeout"] == ""


def test_load_config_file_and_env_override(monkeypatch, tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('provider = "api"\nmodel = "m1"\n', encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", p)
    monkeypatch.setenv("LOOKLIFT_MODEL", "m2")
    cfg = config.load_config()
    assert cfg["provider"] == "api"   # 来自文件
    assert cfg["model"] == "m2"       # env 覆盖文件


def test_timeout_accepts_positive_integer_from_file_and_env(monkeypatch, tmp_path):
    p = tmp_path / "config.toml"
    p.write_text("timeout = 45\n", encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", p)
    assert config.load_config()["timeout"] == 45

    monkeypatch.setenv("LOOKLIFT_TIMEOUT", "90")
    assert config.load_config()["timeout"] == 90


def test_timeout_rejects_invalid_value(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "nonexistent.toml")
    monkeypatch.setenv("LOOKLIFT_TIMEOUT", "soon")
    with pytest.raises(RuntimeError, match="timeout.*正整数"):
        config.load_config()


def test_provider_timeout_defaults_and_override():
    assert config.provider_timeout("cli", "") == 600
    assert config.provider_timeout("api", "") == 120
    assert config.provider_timeout("openai_compat", "") == 120
    assert config.provider_timeout("ollama", "") == 300
    assert config.provider_timeout("ollama", 42) == 42


def test_load_config_include_env_false_skips_env_override(monkeypatch, tmp_path):
    """代码评审(Minor，env-baking):`gui/api.py` 的 `_post_config` 需要一个
    "只读磁盘 + 默认值,不叠加 LOOKLIFT_* 环境变量"的视图当合并基准,否则一次
    保存动作会把进程运行期间生效的环境变量覆盖意外固化进 config.toml。"""
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "nonexistent.toml")
    monkeypatch.setenv("LOOKLIFT_LOOKS_DIR", "/env/path")

    cfg = config.load_config(include_env=False)
    assert cfg["looks_dir"] == ""

    cfg_with_env = config.load_config()
    assert cfg_with_env["looks_dir"] == "/env/path"


def test_looks_dir_prefers_cwd(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "none.toml")
    monkeypatch.delenv("LOOKLIFT_LOOKS_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    (tmp_path / "looks").mkdir()
    assert config.looks_dir() == Path("looks")


def test_looks_dir_falls_back_to_home(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "none.toml")
    monkeypatch.delenv("LOOKLIFT_LOOKS_DIR", raising=False)
    monkeypatch.chdir(tmp_path)  # 无 looks/
    assert config.looks_dir() == Path.home() / ".looklift" / "looks"


def test_save_config_roundtrip(monkeypatch, tmp_path):
    p = tmp_path / "config.toml"
    monkeypatch.setattr(config, "CONFIG_PATH", p)
    config.save_config({
        "provider": "api", "model": "claude-x", "api_key": "sk-123",
        "base_url": "https://example.com", "looks_dir": "", "timeout": 75,
    })
    cfg = config.load_config()
    assert cfg["provider"] == "api"
    assert cfg["model"] == "claude-x"
    assert cfg["api_key"] == "sk-123"
    assert cfg["base_url"] == "https://example.com"
    assert cfg["looks_dir"] == ""
    assert cfg["timeout"] == 75


def test_save_config_quoting_survives_special_chars(monkeypatch, tmp_path):
    p = tmp_path / "config.toml"
    monkeypatch.setattr(config, "CONFIG_PATH", p)
    tricky = 'a "quoted" \\ value'
    config.save_config({"api_key": tricky})
    cfg = config.load_config()
    assert cfg["api_key"] == tricky


def test_save_config_ignores_unknown_keys(monkeypatch, tmp_path):
    p = tmp_path / "config.toml"
    monkeypatch.setattr(config, "CONFIG_PATH", p)
    config.save_config({"provider": "api", "bogus_field": "should not appear"})
    cfg = config.load_config()
    assert cfg["provider"] == "api"
    assert "bogus_field" not in p.read_text(encoding="utf-8")


def test_save_config_creates_parent_dirs(monkeypatch, tmp_path):
    p = tmp_path / "nested" / "dir" / "config.toml"
    monkeypatch.setattr(config, "CONFIG_PATH", p)
    config.save_config({"provider": "api"})
    assert p.is_file()
    assert config.load_config()["provider"] == "api"


def test_looks_dir_uses_config_when_no_cwd_looks(monkeypatch, tmp_path):
    """中间档:cwd 无 looks/,但 config.toml 配了 looks_dir → 用配置路径(优先于 home 兜底)。"""
    cfg_path = tmp_path / "config.toml"
    configured = tmp_path / "mylooks"
    cfg_path.write_text(f'looks_dir = "{configured.as_posix()}"\n', encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_path)
    monkeypatch.delenv("LOOKLIFT_LOOKS_DIR", raising=False)
    monkeypatch.chdir(tmp_path)  # 无 looks/
    assert config.looks_dir() == configured
