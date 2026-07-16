"""配置体系:~/.looklift/config.toml,环境变量 LOOKLIFT_* 覆盖。"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

CONFIG_PATH = Path.home() / ".looklift" / "config.toml"

_DEFAULTS = {"provider": "auto", "model": "", "api_key": "", "base_url": "", "looks_dir": ""}


def load_config() -> dict[str, Any]:
    cfg = dict(_DEFAULTS)
    if CONFIG_PATH.is_file():
        with CONFIG_PATH.open("rb") as f:
            data = tomllib.load(f)
        cfg.update({k: v for k, v in data.items() if k in _DEFAULTS})
    for key in _DEFAULTS:
        env = os.environ.get(f"LOOKLIFT_{key.upper()}")
        if env:
            cfg[key] = env
    return cfg


def looks_dir() -> Path:
    """风格库目录:cwd 下有 looks/ 优先(向后兼容),否则配置项,否则 ~/.looklift/looks/。"""
    local = Path("looks")
    if local.is_dir():
        return local
    configured = load_config()["looks_dir"]
    if configured:
        return Path(configured)
    return Path.home() / ".looklift" / "looks"
