"""内置 Agent Template 的只读目录与白盒契约测试。"""

from __future__ import annotations

import pytest

from looklift.builtin_agent_templates import (
    get_builtin_agent_template,
    list_builtin_agent_templates,
)


def test_builtin_templates_cover_all_three_skills_and_are_readonly() -> None:
    entries = list_builtin_agent_templates()
    assert len(entries) == 6
    assert {entry.template.compatible_skills[0] for entry in entries} == {
        "portrait-natural",
        "product-consistency",
        "highlight-recovery",
    }
    assert all(entry.source == "built_in" and entry.readonly for entry in entries)


def test_builtin_templates_use_only_scalar_relative_operations() -> None:
    for entry in list_builtin_agent_templates():
        assert entry.template.version == 1
        assert entry.template.operations
        assert all(operation.type == "scalar" for operation in entry.template.operations)
        assert all(operation.mode in {"delta", "set"} for operation in entry.template.operations)


def test_template_lookup_rejects_unknown_ids_and_paths() -> None:
    assert get_builtin_agent_template("product-neutral-catalog").template.name == "商品中性目录"
    with pytest.raises(KeyError):
        get_builtin_agent_template("../product-neutral-catalog")

