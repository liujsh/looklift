"""v2.0-B T8：内置模板只读源与用户风格库合并规则。"""
from __future__ import annotations

import json

import pytest
from PIL import Image

from looklift import render
from looklift.gui import lookstore
from looklift.render import contract


def _write_json(directory, name: str, analysis: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{name}.json").write_text(
        json.dumps(analysis, ensure_ascii=False), encoding="utf-8"
    )


def test_default_builtin_source_contains_three_generic_templates():
    entries = lookstore.list_entries(None, lookstore.builtin_looks_dir())

    assert {entry["name"] for entry in entries} == {"青橙经典", "柔和胶片", "清透日系"}
    assert all(entry["source"] == "built_in" for entry in entries)
    assert all(entry["readonly"] is True for entry in entries)
    for entry in entries:
        analysis = lookstore.load(None, entry["name"], lookstore.builtin_looks_dir())
        assert analysis is not None
        assert set(analysis) == {
            "summary", "steps", "basic", "tone_curve", "hsl", "color_grading", "effects"
        }
        for path in contract.param_paths():
            container, key = contract.resolve_path(analysis, path)
            low, high = contract.param_bounds(path)
            assert low <= container[key] <= high, f"{entry['name']} 的 {path} 越界"
        assert render.render(Image.new("RGB", (8, 8), "#808080"), analysis).size == (8, 8)


def test_user_entry_overrides_legacy_same_name_without_duplicate(tmp_path, sample_analysis):
    builtins = tmp_path / "builtins"
    users = tmp_path / "users"
    builtin = {**sample_analysis, "summary": "内置版本"}
    user = {**sample_analysis, "summary": "用户版本"}
    _write_json(builtins, "同名", builtin)
    _write_json(users, "同名", user)

    entries = lookstore.list_entries(users, builtins)

    assert len(entries) == 1
    assert entries[0]["source"] == "user"
    assert entries[0]["readonly"] is False
    assert lookstore.load(users, "同名", builtins)["summary"] == "用户版本"


def test_builtin_name_is_reserved_but_user_directory_remains_writable(tmp_path, sample_analysis):
    builtins = tmp_path / "builtins"
    users = tmp_path / "users"
    _write_json(builtins, "保留名", sample_analysis)

    assert lookstore.exists(users, "保留名", builtins)
    with pytest.raises(PermissionError, match="内置模板只读"):
        lookstore.save(users, "保留名", sample_analysis, builtins)

    lookstore.save(users, "我的风格", sample_analysis, builtins)
    assert (users / "我的风格.json").is_file()
    assert (users / "我的风格.xmp").is_file()
