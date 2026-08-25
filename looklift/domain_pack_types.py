"""Domain Pack 的稳定数据类型与错误契约。"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


class DomainPackError(ValueError):
    """Domain Pack 输入违反内容契约。"""


class DomainPackBudgetError(DomainPackError):
    """必选上下文超过运行预算，不能安全截断。"""


@dataclass(frozen=True)
class VersionedText:
    """一份带稳定身份和版本的 Markdown/文本快照。"""

    source_id: str
    version: int
    content: str


@dataclass(frozen=True)
class VersionedJson:
    """一份带稳定身份和版本的 JSON 数据快照。"""

    source_id: str
    version: int
    value: Any


@dataclass(frozen=True)
class StyleProfile:
    """用户明确确认的结构化风格偏好。"""

    profile_id: str
    version: int
    scope: str
    confirmed: bool
    preferences: Mapping[str, str]
    avoid: tuple[str, ...] = ()


@dataclass(frozen=True)
class DomainPackRequest:
    """编译一次运行所需的全部已解析领域来源。"""

    system_contract: VersionedText
    domain_contract: VersionedText
    tool_contract: VersionedJson
    user_goal: str
    run_context: Mapping[str, Any]
    permission_contract: VersionedJson | None = None
    style_profile: StyleProfile | None = None
    skill: VersionedText | None = None
    template: VersionedJson | None = None
    references: tuple[VersionedText, ...] = field(default_factory=tuple)
    global_rules: tuple[VersionedText, ...] = field(default_factory=tuple)
    memory: tuple[VersionedText, ...] = field(default_factory=tuple)
    project_context: tuple[VersionedText, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class SourceFingerprint:
    """一次运行实际解析到的领域来源指纹。"""

    version: int
    content_hash: str


@dataclass(frozen=True)
class CompiledDomainPack:
    """供 Harness Adapter 消费且可持久化复现的编译结果。"""

    instructions: str
    user_message: str
    source_hashes: tuple[tuple[str, SourceFingerprint], ...]
    omitted_sources: tuple[str, ...]
    content_hash: str
    estimated_tokens: int
