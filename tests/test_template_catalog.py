"""v2.4 模板目录：官方教学元数据与用户模板降级。"""
from __future__ import annotations

import json

from looklift.gui import template_catalog


def _write_look(directory, name: str, analysis: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.json").write_text(
        json.dumps(analysis, ensure_ascii=False), encoding="utf-8"
    )


def test_catalog_combines_official_lesson_without_copying_parameter_values(tmp_path):
    builtins = tmp_path / "builtins"
    users = tmp_path / "users"
    analysis = {
        "summary": "冷暖分离",
        "steps": ["先压高光", "再调整阴影色相"],
        "basic": {"contrast": 18, "highlights": -20},
        "effects": {"grain_amount": 0},
    }
    _write_look(builtins, "青橙经典", analysis)
    metadata = tmp_path / "lessons.json"
    metadata.write_text(json.dumps({
        "青橙经典": {
            "suitable_for": ["旅行", "城市夜景"],
            "principles": ["用冷暖互补建立画面层次"],
            "key_paths": ["basic.highlights", "basic.contrast"],
        }
    }, ensure_ascii=False), encoding="utf-8")

    cards = template_catalog.list_cards(users, builtins, metadata)

    assert cards == [{
        "name": "青橙经典",
        "source": "built_in",
        "readonly": True,
        "summary": "冷暖分离",
        "suitable_for": ["旅行", "城市夜景"],
        "principles": ["用冷暖互补建立画面层次"],
        "steps": ["先压高光", "再调整阴影色相"],
        "key_parameters": [
            {"path": "basic.highlights", "value": -20},
            {"path": "basic.contrast", "value": 18},
        ],
    }]


def test_catalog_derives_safe_user_lesson_and_skips_corrupt_look(tmp_path):
    builtins = tmp_path / "builtins"
    users = tmp_path / "users"
    _write_look(users, "我的风格", {
        "summary": "低饱和人像",
        "steps": ["降低整体饱和度"],
        "basic": {"exposure": 0, "saturation": -16, "contrast": 8},
        "effects": {"vignette_amount": -5},
    })
    (users / "损坏.json").write_text("{", encoding="utf-8")

    cards = template_catalog.list_cards(users, builtins, tmp_path / "missing.json")

    assert len(cards) == 1
    card = cards[0]
    assert card["name"] == "我的风格"
    assert card["source"] == "user"
    assert card["readonly"] is False
    assert card["suitable_for"] == ["按当前照片继续微调"]
    assert card["principles"] == ["这是你的白盒参数组合，可展开关键参数继续学习和修改。"]
    assert card["steps"] == ["降低整体饱和度"]
    assert card["key_parameters"] == [
        {"path": "basic.saturation", "value": -16},
        {"path": "basic.contrast", "value": 8},
        {"path": "effects.vignette_amount", "value": -5},
    ]
