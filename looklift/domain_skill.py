"""LookLift 内置修图 Skill 的受限 frontmatter 协议与加载器。"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from dataclasses import dataclass
from importlib.resources import files

from .domain_pack_types import VersionedText


_BUILTIN_SKILLS = {
    "portrait-natural": (
        ("data", "skills", "portrait-natural", "SKILL.md"),
        1,
        "af7c7a1517226482e84bca2d2b09efb22229dc250b72b391334a0c37de7cd0c8",
    ),
}
_METADATA_FIELDS = frozenset(
    {
        "id",
        "version",
        "name",
        "applies_to",
        "relevant_parameter_groups",
        "references",
        "required_engine_capabilities",
    }
)
_REQUIRED_SECTIONS = (
    "## 目标",
    "## 适用范围",
    "## 不适用范围",
    "## 诊断重点",
    "## 条件化调整策略",
    "## 复核清单",
    "## 停止与降级",
    "## 输出要求",
)
_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9./-]*")
_REFERENCE_TOKEN_PATTERN = re.compile(r"[a-z0-9./-]+")


class DomainSkillError(ValueError):
    """Skill 元数据、正文、引用或引擎兼容性不合法。"""


@dataclass(frozen=True)
class DomainSkill:
    """已经过协议校验的单个修图 Skill。"""

    skill_id: str
    version: int
    name: str
    applies_to: tuple[str, ...]
    relevant_parameter_groups: tuple[str, ...]
    references: tuple[str, ...]
    required_engine_capabilities: tuple[str, ...]
    body: str
    source_content: str

    def to_versioned_text(self) -> VersionedText:
        """转换成 Context Compiler 可消费且可快照的来源。"""
        return VersionedText(
            source_id=f"skill.{self.skill_id}",
            version=self.version,
            content=self.source_content,
        )


def load_builtin_skill(
    skill_id: str,
    *,
    engine_capabilities: Iterable[str],
) -> DomainSkill:
    """按白名单加载内置 Skill，并校验当前引擎能力。"""
    registration = _BUILTIN_SKILLS.get(skill_id)
    if registration is None:
        raise DomainSkillError(f"未知内置 Skill：{skill_id}")
    relative_path, expected_version, expected_hash = registration
    try:
        content = files("looklift").joinpath(*relative_path).read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise DomainSkillError(f"内置 Skill 文件缺失：{skill_id}") from exc

    normalized = _normalize_content(content)
    actual_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    if actual_hash != expected_hash:
        raise DomainSkillError("内置 Skill 内容与注册版本摘要不一致")
    skill = parse_domain_skill(normalized)
    if skill.skill_id != skill_id:
        raise DomainSkillError("内置 Skill 文件 ID 与注册 ID 不一致")
    if skill.version != expected_version:
        raise DomainSkillError("内置 Skill 文件版本与注册版本不一致")
    available = frozenset(engine_capabilities)
    missing = set(skill.required_engine_capabilities) - available
    if missing:
        raise DomainSkillError(f"缺少引擎能力：{', '.join(sorted(missing))}")
    return skill


def parse_domain_skill(content: str) -> DomainSkill:
    """解析无嵌套、无类型推断的受限 YAML frontmatter。"""
    normalized = _normalize_content(content)
    header, separator, body = normalized[4:].partition("\n---\n")
    if not separator or not body.strip():
        raise DomainSkillError("Skill 必须包含闭合 frontmatter 和正文")
    metadata = _parse_metadata(header)

    skill_id = metadata["id"]
    if not _ID_PATTERN.fullmatch(skill_id):
        raise DomainSkillError("Skill id 必须是小写 hyphen-case")
    version = _parse_version(metadata["version"])
    name = metadata["name"].strip()
    if not name:
        raise DomainSkillError("Skill name 不能为空")

    applies_to = _parse_list(metadata["applies_to"], "applies_to")
    parameter_groups = _parse_list(
        metadata["relevant_parameter_groups"],
        "relevant_parameter_groups",
    )
    references = _parse_list(
        metadata["references"],
        "references",
        allow_empty=True,
        pattern=_REFERENCE_TOKEN_PATTERN,
    )
    capabilities = _parse_list(
        metadata["required_engine_capabilities"],
        "required_engine_capabilities",
    )
    _validate_references(references)
    _validate_sections(body)
    return DomainSkill(
        skill_id=skill_id,
        version=version,
        name=name,
        applies_to=applies_to,
        relevant_parameter_groups=parameter_groups,
        references=references,
        required_engine_capabilities=capabilities,
        body=body.strip(),
        source_content=normalized,
    )


def _normalize_content(content: str) -> str:
    if not isinstance(content, str):
        raise DomainSkillError("Skill 内容必须是文本")
    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized.startswith("---\n"):
        raise DomainSkillError("Skill 必须以 YAML frontmatter 开始")
    return normalized


def _parse_metadata(header: str) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for line in header.splitlines():
        key, separator, value = line.partition(":")
        key = key.strip()
        if not separator or not key or not value.strip():
            raise DomainSkillError(f"无效 Skill 元数据行：{line}")
        if key not in _METADATA_FIELDS:
            raise DomainSkillError(f"未知元数据：{key}")
        if key in metadata:
            raise DomainSkillError(f"重复元数据：{key}")
        metadata[key] = value.strip()
    missing = _METADATA_FIELDS - metadata.keys()
    if missing:
        raise DomainSkillError(f"缺少元数据：{', '.join(sorted(missing))}")
    return metadata


def _parse_version(value: str) -> int:
    if not value.isascii() or not value.isdecimal() or int(value) < 1:
        raise DomainSkillError("Skill version 必须是正整数")
    return int(value)


def _parse_list(
    value: str,
    label: str,
    *,
    allow_empty: bool = False,
    pattern: re.Pattern[str] = _TOKEN_PATTERN,
) -> tuple[str, ...]:
    if not value.startswith("[") or not value.endswith("]"):
        raise DomainSkillError(f"{label} 必须使用内联数组")
    inner = value[1:-1].strip()
    if not inner:
        if allow_empty:
            return ()
        raise DomainSkillError(f"{label} 不能为空")
    items = tuple(item.strip() for item in inner.split(","))
    if any(not pattern.fullmatch(item) for item in items):
        raise DomainSkillError(f"{label} 包含非法值")
    if len(set(items)) != len(items):
        raise DomainSkillError(f"{label} 包含重复值")
    return items


def _validate_references(references: tuple[str, ...]) -> None:
    if len(references) > 4:
        raise DomainSkillError("单个 Skill 最多声明四个 Reference")
    for reference in references:
        if (
            not reference.startswith("knowledge/")
            or not reference.endswith(".md")
            or ".." in reference
            or "\\" in reference
        ):
            raise DomainSkillError(f"非法 Reference 路径：{reference}")


def _validate_sections(body: str) -> None:
    try:
        positions = [body.index(section) for section in _REQUIRED_SECTIONS]
    except ValueError as exc:
        raise DomainSkillError("Skill 正文缺少固定领域章节") from exc
    if positions != sorted(positions):
        raise DomainSkillError("Skill 正文章节顺序不合法")
