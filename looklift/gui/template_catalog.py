"""把现有风格库投影成带教学信息的模板目录。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import lookstore

_DEFAULT_LESSONS = Path(__file__).resolve().parents[1] / "data" / "template_lessons.json"
_USER_PRINCIPLE = "这是你的白盒参数组合，可展开关键参数继续学习和修改。"
_KEY_LIMIT = 6


def _read_lessons(path: Path) -> dict[str, dict[str, Any]]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(value, dict):
        return {}
    return {name: lesson for name, lesson in value.items() if isinstance(lesson, dict)}


def _value_at_path(analysis: dict[str, Any], path: str) -> int | float | None:
    value: Any = analysis
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _official_parameters(
    analysis: dict[str, Any], paths: Any,
) -> list[dict[str, int | float | str]]:
    if not isinstance(paths, list):
        return []
    result = []
    for path in paths:
        if not isinstance(path, str):
            continue
        value = _value_at_path(analysis, path)
        if value is not None:
            result.append({"path": path, "value": value})
    return result[:_KEY_LIMIT]


def _user_parameters(analysis: dict[str, Any]) -> list[dict[str, int | float | str]]:
    values: list[tuple[float, str, int | float]] = []
    for section in ("basic", "effects"):
        group = analysis.get(section)
        if not isinstance(group, dict):
            continue
        for key, value in group.items():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or value == 0:
                continue
            values.append((abs(float(value)), f"{section}.{key}", value))
    values.sort(key=lambda item: (-item[0], item[1]))
    return [{"path": path, "value": value} for _, path, value in values[:_KEY_LIMIT]]


def _strings(value: Any) -> list[str]:
    return [item for item in value if isinstance(item, str)] if isinstance(value, list) else []


def list_cards(
    looks_dir: Path | None,
    builtins_dir: Path | None = None,
    lessons_path: Path | None = None,
) -> list[dict[str, Any]]:
    """返回平台模板卡片；用户 look 不需要迁移或额外元数据。"""
    builtins = lookstore.builtin_looks_dir() if builtins_dir is None else builtins_dir
    lessons = _read_lessons(_DEFAULT_LESSONS if lessons_path is None else lessons_path)
    cards = []
    for entry in lookstore.list_entries(looks_dir, builtins):
        analysis = lookstore.load(looks_dir, entry["name"], builtins)
        if not isinstance(analysis, dict):
            continue
        lesson = lessons.get(entry["name"], {}) if entry["source"] == "built_in" else {}
        official = bool(lesson)
        cards.append({
            "name": entry["name"],
            "source": entry["source"],
            "readonly": entry["readonly"],
            "summary": analysis.get("summary") if isinstance(analysis.get("summary"), str) else "",
            "suitable_for": _strings(lesson.get("suitable_for")) if official else ["按当前照片继续微调"],
            "principles": _strings(lesson.get("principles")) if official else [_USER_PRINCIPLE],
            "steps": _strings(analysis.get("steps")),
            "key_parameters": _official_parameters(analysis, lesson.get("key_paths"))
            if official else _user_parameters(analysis),
        })
    return cards
