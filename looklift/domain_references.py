"""按 Skill 声明加载少量版本化摄影知识 Reference。"""

from __future__ import annotations

import hashlib
from importlib.resources import files

from .domain_pack_types import VersionedText
from .domain_skill import DomainSkill, DomainSkillError


_REFERENCE_REGISTRY = {
    "knowledge/light.md": (
        ("data", "skills", "knowledge", "light.md"),
        "knowledge.light",
        1,
        "274f98f53b30a56a080d768e1a810246eb71b251208927c5b6565ac612fdfe7e",
    ),
    "knowledge/color.md": (
        ("data", "skills", "knowledge", "color.md"),
        "knowledge.color",
        1,
        "03ad9eece627f006e6d714da4081d78fcfe7db064c546dbff33f11a933908ecf",
    ),
}


def load_skill_references(skill: DomainSkill) -> tuple[VersionedText, ...]:
    """只解析当前 Skill 显式声明并在内置注册表中的 Reference。"""
    return tuple(_load_reference(reference) for reference in skill.references)


def _load_reference(reference: str) -> VersionedText:
    registration = _REFERENCE_REGISTRY.get(reference)
    if registration is None:
        raise DomainSkillError(f"Skill 声明了未知 Reference：{reference}")
    relative_path, source_id, version, expected_hash = registration
    try:
        content = files("looklift").joinpath(*relative_path).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise DomainSkillError(f"内置 Reference 文件缺失：{reference}") from exc

    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise DomainSkillError(f"内置 Reference 内容为空：{reference}")
    actual_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    if actual_hash != expected_hash:
        raise DomainSkillError(f"内置 Reference 与注册版本摘要不一致：{reference}")
    return VersionedText(source_id=source_id, version=version, content=normalized)
