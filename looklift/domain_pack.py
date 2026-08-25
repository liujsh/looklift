"""v2.6 修图 Domain Pack 的纯数据编译器。"""
from __future__ import annotations

import hashlib
import json
from html import escape
from typing import Any

from .domain_pack_types import (
    CompiledDomainPack,
    DomainPackBudgetError,
    DomainPackError,
    DomainPackRequest,
    SourceFingerprint,
    StyleProfile,
    VersionedJson,
    VersionedText,
)


_STYLE_DIMENSIONS = frozenset(
    {"overall", "exposure", "contrast", "color", "portrait", "texture"}
)
_STYLE_SCOPES = frozenset({"global", "project", "run"})


def compile_domain_pack(
    request: DomainPackRequest,
    *,
    max_prompt_chars: int | None = None,
) -> CompiledDomainPack:
    """按固定优先级编译领域上下文，预算不足时只省略 Reference。"""
    if max_prompt_chars is not None and max_prompt_chars <= 0:
        raise DomainPackBudgetError("Prompt 字符预算必须为正数")

    system = _text_snapshot(request.system_contract)
    domain = _text_snapshot(request.domain_contract)
    tools = _json_snapshot(request.tool_contract)
    goal = _required_text(request.user_goal, "用户目标")
    run_context = _canonical_json(request.run_context, "运行上下文")

    prefix = [
        _text_section("SYSTEM_BOUNDARIES", request.system_contract, system),
        _text_section("PHOTO_EDITING_CONTRACT", request.domain_contract, domain),
        _plain_json_section("RUN_CONTEXT", run_context),
    ]
    sources: list[tuple[str, SourceFingerprint]] = [
        _fingerprint(request.system_contract.source_id, request.system_contract.version, system),
        _fingerprint(request.domain_contract.source_id, request.domain_contract.version, domain),
    ]

    if request.style_profile is not None:
        profile_json = _style_snapshot(request.style_profile)
        prefix.append(
            _plain_json_section(
                "STYLE_PROFILE",
                profile_json,
                source_id=request.style_profile.profile_id,
                version=request.style_profile.version,
            )
        )
        sources.append(
            _fingerprint(
                request.style_profile.profile_id,
                request.style_profile.version,
                profile_json,
            )
        )

    if request.skill is not None:
        skill = _text_snapshot(request.skill)
        prefix.append(_text_section("SELECTED_SKILL", request.skill, skill))
        sources.append(_fingerprint(request.skill.source_id, request.skill.version, skill))

    if request.template is not None:
        template = _json_snapshot(request.template)
        prefix.append(
            _json_section("SELECTED_TEMPLATE", request.template, template)
        )
        sources.append(
            _fingerprint(request.template.source_id, request.template.version, template)
        )

    reference_values: list[tuple[VersionedText, str]] = []
    for reference in request.references:
        content = _text_snapshot(reference)
        reference_values.append((reference, content))
        sources.append(_fingerprint(reference.source_id, reference.version, content))

    sources.append(
        _fingerprint(request.tool_contract.source_id, request.tool_contract.version, tools)
    )
    _ensure_unique_source_ids(sources)

    suffix = [_json_section("TOOL_CONTRACT", request.tool_contract, tools)]
    required = _join_sections(prefix + suffix)
    if max_prompt_chars is not None and len(required) > max_prompt_chars:
        raise DomainPackBudgetError("Domain Pack 必选内容超过 Prompt 字符预算，不能截断")

    kept_references: list[tuple[VersionedText, str]] = []
    omitted: list[str] = []
    for reference, content in reference_values:
        candidate_references = kept_references + [(reference, content)]
        candidate = _join_sections(
            prefix + [_references_section(candidate_references)] + suffix
        )
        if max_prompt_chars is None or len(candidate) <= max_prompt_chars:
            kept_references = candidate_references
        else:
            omitted.append(reference.source_id)

    sections = list(prefix)
    if kept_references:
        sections.append(_references_section(kept_references))
    sections.extend(suffix)
    instructions = _join_sections(sections)

    ordered_sources = tuple(sorted(sources, key=lambda item: item[0]))
    digest_payload = _canonical_json(
        {
            "instructions": instructions,
            "user_message": goal,
            "sources": [
                {
                    "id": source_id,
                    "version": fingerprint.version,
                    "hash": fingerprint.content_hash,
                }
                for source_id, fingerprint in ordered_sources
            ],
            "omitted_sources": omitted,
        },
        "编译结果",
    )
    return CompiledDomainPack(
        instructions=instructions,
        user_message=goal,
        source_hashes=ordered_sources,
        omitted_sources=tuple(omitted),
        content_hash=_sha256(digest_payload),
        estimated_tokens=max(1, (len(instructions) + len(goal) + 3) // 4),
    )


def _text_snapshot(document: VersionedText) -> str:
    _validate_source(document.source_id, document.version)
    return _required_text(document.content, f"来源 {document.source_id}")


def _json_snapshot(document: VersionedJson) -> str:
    _validate_source(document.source_id, document.version)
    return _canonical_json(document.value, f"来源 {document.source_id}")


def _style_snapshot(profile: StyleProfile) -> str:
    _validate_source(profile.profile_id, profile.version)
    unknown = set(profile.preferences) - _STYLE_DIMENSIONS
    if unknown:
        raise DomainPackError(f"未知风格维度：{', '.join(sorted(unknown))}")
    if profile.scope not in _STYLE_SCOPES:
        raise DomainPackError(f"未知 StyleProfile 作用域：{profile.scope}")
    if not profile.confirmed:
        raise DomainPackError("StyleProfile 必须经过用户确认")

    preferences: dict[str, str] = {}
    for key, value in profile.preferences.items():
        preferences[key] = _required_text(value, f"风格维度 {key}")
    avoid = [_required_text(item, "风格避免项") for item in profile.avoid]
    return _canonical_json(
        {
            "id": profile.profile_id,
            "version": profile.version,
            "scope": profile.scope,
            "preferences": preferences,
            "avoid": avoid,
        },
        "StyleProfile",
    )


def _canonical_json(value: Any, label: str) -> str:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DomainPackError(f"{label} 必须是合法 JSON 数据") from exc
    # 结构化用户内容会被嵌入 XML 风格分区；转义分隔字符，避免内容伪造闭合标签。
    return encoded.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DomainPackError(f"{label} 内容不能为空")
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def _validate_source(source_id: str, version: int) -> None:
    if not isinstance(source_id, str) or not source_id.strip():
        raise DomainPackError("领域来源 ID 不能为空")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise DomainPackError(f"来源 {source_id} 的版本必须是正整数")


def _fingerprint(source_id: str, version: int, content: str) -> tuple[str, SourceFingerprint]:
    return source_id, SourceFingerprint(version=version, content_hash=_sha256(content))


def _ensure_unique_source_ids(sources: list[tuple[str, SourceFingerprint]]) -> None:
    seen: set[str] = set()
    for source_id, _ in sources:
        if source_id in seen:
            raise DomainPackError(f"领域来源 ID 重复：{source_id}")
        seen.add(source_id)


def _text_section(tag: str, document: VersionedText, content: str) -> str:
    return f"<{tag}{_source_attributes(document.source_id, document.version)}>\n{content}\n</{tag}>"


def _json_section(tag: str, document: VersionedJson, content: str) -> str:
    return f"<{tag}{_source_attributes(document.source_id, document.version)}>\n{content}\n</{tag}>"


def _plain_json_section(
    tag: str,
    content: str,
    *,
    source_id: str | None = None,
    version: int | None = None,
) -> str:
    attributes = "" if source_id is None else _source_attributes(source_id, version or 1)
    return f"<{tag}{attributes}>\n{content}\n</{tag}>"


def _references_section(references: list[tuple[VersionedText, str]]) -> str:
    body = "\n\n".join(
        f"<REFERENCE{_source_attributes(document.source_id, document.version)}>\n"
        f"{content}\n</REFERENCE>"
        for document, content in references
    )
    return f"<REFERENCES>\n{body}\n</REFERENCES>"


def _source_attributes(source_id: str, version: int) -> str:
    return f' source_id="{escape(source_id, quote=True)}" version="{version}"'


def _join_sections(sections: list[str]) -> str:
    return "\n\n".join(sections)


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
