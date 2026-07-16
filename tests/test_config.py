import os
from pathlib import Path
from looklift import config


def test_load_config_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "nonexistent.toml")
    for k in list(os.environ):
        if k.startswith("LOOKLIFT_"):
            monkeypatch.delenv(k)
    cfg = config.load_config()
    assert cfg["provider"] == "auto"
    assert cfg["api_key"] == ""


def test_load_config_file_and_env_override(monkeypatch, tmp_path):
    p = tmp_path / "config.toml"
    p.write_text('provider = "api"\nmodel = "m1"\n', encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", p)
    monkeypatch.setenv("LOOKLIFT_MODEL", "m2")
    cfg = config.load_config()
    assert cfg["provider"] == "api"   # 来自文件
    assert cfg["model"] == "m2"       # env 覆盖文件


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


def test_looks_dir_uses_config_when_no_cwd_looks(monkeypatch, tmp_path):
    """中间档:cwd 无 looks/,但 config.toml 配了 looks_dir → 用配置路径(优先于 home 兜底)。"""
    cfg_path = tmp_path / "config.toml"
    configured = tmp_path / "mylooks"
    cfg_path.write_text(f'looks_dir = "{configured.as_posix()}"\n', encoding="utf-8")
    monkeypatch.setattr(config, "CONFIG_PATH", cfg_path)
    monkeypatch.delenv("LOOKLIFT_LOOKS_DIR", raising=False)
    monkeypatch.chdir(tmp_path)  # 无 looks/
    assert config.looks_dir() == configured
