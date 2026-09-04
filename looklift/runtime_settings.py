"""CLI 启停与默认入口的本地设置。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import CONFIG_PATH


def settings_path() -> Path:
    return CONFIG_PATH.parent / "runtime-settings.json"


def load_runtime_settings() -> dict[str, Any]:
    path = settings_path()
    if not path.is_file():
        return {"enabled": {}, "default_runtime_id": None, "default_model": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"enabled": {}, "default_runtime_id": None, "default_model": None}
    enabled = data.get("enabled", {})
    return {"enabled": enabled if isinstance(enabled, dict) else {}, "default_runtime_id": data.get("default_runtime_id"), "default_model": data.get("default_model")}


def save_runtime_settings(data: dict[str, Any]) -> dict[str, Any]:
    normalized = {"enabled": {str(k): bool(v) for k, v in data.get("enabled", {}).items()}, "default_runtime_id": data.get("default_runtime_id"), "default_model": data.get("default_model")}
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return normalized
