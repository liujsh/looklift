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


def save_config(data: dict) -> None:
    """把 data 写入 CONFIG_PATH,手写简单 TOML 序列化(值仅支持 str/int/float)。

    只序列化 `_DEFAULTS` 里声明的已知字段,忽略其余 key(避免配置向导传入的
    杂项字段污染 config.toml);自动创建父目录。
    """
    lines = [f"{key} = {_toml_value(data[key])}" for key in _DEFAULTS if key in data]
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines)
    if text:
        text += "\n"
    CONFIG_PATH.write_text(text, encoding="utf-8")


def _toml_value(value: Any) -> str:
    """把单个值序列化成 TOML 字面量;字符串用双引号包裹并转义反斜杠/双引号。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def looks_dir() -> Path:
    """风格库目录:cwd 下有 looks/ 优先(向后兼容),否则配置项,否则 ~/.looklift/looks/。"""
    local = Path("looks")
    if local.is_dir():
        return local
    configured = load_config()["looks_dir"]
    if configured:
        return Path(configured)
    return Path.home() / ".looklift" / "looks"
