"""LookLift 受限修图 Skill 协议与内置 Skill 测试。"""

from __future__ import annotations

import pytest

from looklift.domain_skill import (
    DomainSkillError,
    load_builtin_skill,
    parse_domain_skill,
)
from looklift.domain_references import load_skill_references


_ENGINE_CAPABILITIES = {"global-adjustments", "candidate-render"}


def test_load_natural_portrait_skill_with_versioned_metadata() -> None:
    skill = load_builtin_skill(
        "portrait-natural",
        engine_capabilities=_ENGINE_CAPABILITIES,
    )

    assert skill.skill_id == "portrait-natural"
    assert skill.version == 1
    assert skill.name == "自然人像"
    assert skill.applies_to == ("portrait",)
    assert skill.relevant_parameter_groups == ("light", "color", "detail")
    assert skill.references == ("knowledge/light.md", "knowledge/color.md")
    assert skill.required_engine_capabilities == (
        "global-adjustments",
        "candidate-render",
    )


@pytest.mark.parametrize(
    ("skill_id", "name", "applies_to"),
    [
        ("portrait-natural", "自然人像", ("portrait",)),
        ("product-consistency", "商品一致性", ("product",)),
        ("highlight-recovery", "高光与曝光恢复", ("highlight", "exposure")),
    ],
)
def test_all_builtin_skills_have_versioned_contract_and_references(
    skill_id: str,
    name: str,
    applies_to: tuple[str, ...],
) -> None:
    skill = load_builtin_skill(skill_id, engine_capabilities=_ENGINE_CAPABILITIES)

    assert skill.name == name
    assert skill.applies_to == applies_to
    assert skill.version == 1
    assert skill.references == ("knowledge/light.md", "knowledge/color.md")
    assert "insufficient_capability" in skill.body


def test_skill_body_contains_complete_domain_decision_loop() -> None:
    skill = load_builtin_skill(
        "portrait-natural",
        engine_capabilities=_ENGINE_CAPABILITIES,
    )

    expected_sections = (
        "## 目标",
        "## 适用范围",
        "## 不适用范围",
        "## 诊断重点",
        "## 条件化调整策略",
        "## 复核清单",
        "## 停止与降级",
        "## 输出要求",
    )
    positions = [skill.body.index(section) for section in expected_sections]
    assert positions == sorted(positions)
    assert "先观察" in skill.body
    assert "查看候选预览" in skill.body
    assert "insufficient_capability" in skill.body


def test_skill_exposes_versioned_prompt_source_without_losing_metadata() -> None:
    skill = load_builtin_skill(
        "portrait-natural",
        engine_capabilities=_ENGINE_CAPABILITIES,
    )

    source = skill.to_versioned_text()

    assert source.source_id == "skill.portrait-natural"
    assert source.version == 1
    assert "id: portrait-natural" in source.content
    assert "## 诊断重点" in source.content


def test_skill_only_loads_its_declared_versioned_references() -> None:
    skill = load_builtin_skill(
        "portrait-natural",
        engine_capabilities=_ENGINE_CAPABILITIES,
    )

    references = load_skill_references(skill)

    assert [(item.source_id, item.version) for item in references] == [
        ("knowledge.light", 1),
        ("knowledge.color", 1),
    ]
    assert "高光" in references[0].content
    assert "肤色" in references[1].content


def test_skill_rejects_missing_engine_capability() -> None:
    with pytest.raises(DomainSkillError, match="缺少引擎能力.*candidate-render"):
        load_builtin_skill(
            "portrait-natural",
            engine_capabilities={"global-adjustments"},
        )


@pytest.mark.parametrize("skill_id", ["../portrait-natural", "Portrait", "unknown"])
def test_builtin_skill_selection_does_not_accept_paths_or_unknown_ids(
    skill_id: str,
) -> None:
    with pytest.raises(DomainSkillError, match="内置 Skill"):
        load_builtin_skill(skill_id, engine_capabilities=_ENGINE_CAPABILITIES)


def test_parser_rejects_reference_traversal() -> None:
    content = """---
id: unsafe-skill
version: 1
name: 不安全技能
applies_to: [portrait]
relevant_parameter_groups: [light]
references: [../secret.md]
required_engine_capabilities: [candidate-render]
---
## 目标
测试
"""

    with pytest.raises(DomainSkillError, match="Reference 路径"):
        parse_domain_skill(content)


def test_parser_rejects_unknown_or_duplicate_metadata() -> None:
    unknown = """---
id: sample
version: 1
name: 示例
applies_to: [portrait]
relevant_parameter_groups: [light]
references: []
required_engine_capabilities: [candidate-render]
prompt_override: true
---
正文
"""
    duplicate = unknown.replace(
        "prompt_override: true",
        "name: 重复名称",
    )

    with pytest.raises(DomainSkillError, match="未知元数据"):
        parse_domain_skill(unknown)
    with pytest.raises(DomainSkillError, match="重复元数据"):
        parse_domain_skill(duplicate)
