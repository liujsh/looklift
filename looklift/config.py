"""配置体系:~/.looklift/config.toml,环境变量 LOOKLIFT_* 覆盖。"""
from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

CONFIG_PATH = Path.home() / ".looklift" / "config.toml"

_DEFAULTS = {
    "provider": "auto",
    "model": "",
    "api_key": "",
    "base_url": "",
    "looks_dir": "",
    "timeout": "",
}

_PROVIDER_TIMEOUTS = {"cli": 600, "api": 120, "openai_compat": 120, "ollama": 300}


def load_config(*, include_env: bool = True) -> dict[str, Any]:
    """读 `_DEFAULTS` + 磁盘文件 + （默认）`LOOKLIFT_*` 环境变量覆盖。

    `include_env=False` 跳过环境变量这一层，只要「默认值 + 磁盘文件」——
    给"把当前落盘配置当合并基准做部分更新"这种场景用（见 gui/api.py 的
    `_post_config`）：环境变量是这次进程运行期间的临时覆盖，不该被一次保存
    动作意外固化进 config.toml。
    """
    cfg = dict(_DEFAULTS)
    if CONFIG_PATH.is_file():
        with CONFIG_PATH.open("rb") as f:
            data = tomllib.load(f)
        cfg.update({k: v for k, v in data.items() if k in _DEFAULTS})
    if include_env:
        for key in _DEFAULTS:
            env = os.environ.get(f"LOOKLIFT_{key.upper()}")
            if env:
                cfg[key] = env
    if cfg["timeout"] != "":
        cfg["timeout"] = _positive_timeout(cfg["timeout"])
    return cfg


def provider_timeout(provider: str, value: Any = "") -> int:
    """解析 provider 超时秒数；空值采用各后端默认值。"""
    if value == "":
        try:
            return _PROVIDER_TIMEOUTS[provider]
        except KeyError:
            raise RuntimeError(f"未知 provider：{provider}") from None
    return _positive_timeout(value)


def _positive_timeout(value: Any) -> int:
    """把配置值规范成正整数秒。"""
    if isinstance(value, bool):
        raise RuntimeError("timeout 必须是正整数秒。")
    try:
        timeout = int(value)
    except (TypeError, ValueError):
        raise RuntimeError("timeout 必须是正整数秒。") from None
    if timeout <= 0 or isinstance(value, float) and not value.is_integer():
        raise RuntimeError("timeout 必须是正整数秒。")
    return timeout


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
