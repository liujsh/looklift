"""Domain Pack 的 JSON 快照、完整性检查与规范化恢复。"""
from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .domain_pack import compile_domain_pack
from .domain_pack_types import (
    CompiledDomainPack,
    DomainPackError,
    DomainPackRequest,
    StyleProfile,
    VersionedJson,
    VersionedText,
)


_SCHEMA_VERSION = 1


class DomainPackSnapshotError(ValueError):
    """Domain Pack 快照损坏、格式未知或无法复现。"""


@dataclass(frozen=True)
class RestoredDomainPack:
    """从持久化快照重新校验并编译的运行输入。"""

    request: DomainPackRequest
    compiled: CompiledDomainPack
    max_prompt_chars: int | None


def create_domain_pack_snapshot(
    request: DomainPackRequest,
    *,
    max_prompt_chars: int | None = None,
) -> dict[str, Any]:
    """保存完整来源和编译摘要；Hash 用于发现损坏，不替代可信签名。"""
    compiled = compile_domain_pack(request, max_prompt_chars=max_prompt_chars)
    payload: dict[str, Any] = {
        "schema_version": _SCHEMA_VERSION,
        "max_prompt_chars": max_prompt_chars,
        "request": _request_to_dict(request),
        "compiled": _compiled_summary(compiled),
    }
    snapshot = _json_clone(payload, "Domain Pack 快照")
    snapshot["snapshot_hash"] = _snapshot_hash(snapshot)
    return snapshot


def restore_domain_pack_snapshot(value: Any) -> RestoredDomainPack:
    """验证快照完整性，重建强类型请求并重新编译核对语义摘要。"""
    snapshot = _mapping(value, "Domain Pack 快照")
    if snapshot.get("schema_version") != _SCHEMA_VERSION:
        raise DomainPackSnapshotError("不支持的 Domain Pack 快照格式版本")

    stored_hash = snapshot.get("snapshot_hash")
    if not isinstance(stored_hash, str) or len(stored_hash) != 64:
        raise DomainPackSnapshotError("Domain Pack 快照缺少合法 snapshot_hash")
    if not _constant_hash_equal(stored_hash, _snapshot_hash(snapshot)):
        raise DomainPackSnapshotError("Domain Pack 快照完整性校验失败")

    max_prompt_chars = snapshot.get("max_prompt_chars")
    if max_prompt_chars is not None and (
        not isinstance(max_prompt_chars, int)
        or isinstance(max_prompt_chars, bool)
        or max_prompt_chars <= 0
    ):
        raise DomainPackSnapshotError("快照中的 Prompt 字符预算无效")

    try:
        request = _request_from_dict(snapshot.get("request"))
        compiled = compile_domain_pack(request, max_prompt_chars=max_prompt_chars)
    except (DomainPackError, KeyError, TypeError, ValueError) as exc:
        raise DomainPackSnapshotError("Domain Pack 快照内容无法恢复") from exc

    expected_summary = _compiled_summary(compiled)
    stored_summary = _mapping(snapshot.get("compiled"), "编译摘要")
    if stored_summary != expected_summary:
        raise DomainPackSnapshotError("Domain Pack 快照编译摘要与重新编译结果不一致")
    return RestoredDomainPack(
        request=request,
        compiled=compiled,
        max_prompt_chars=max_prompt_chars,
    )


def _request_to_dict(request: DomainPackRequest) -> dict[str, Any]:
    return {
        "system_contract": _text_to_dict(request.system_contract),
        "domain_contract": _text_to_dict(request.domain_contract),
        "tool_contract": _json_to_dict(request.tool_contract),
        "user_goal": request.user_goal,
        "run_context": request.run_context,
        "style_profile": _style_to_dict(request.style_profile),
        "skill": _text_to_dict(request.skill) if request.skill is not None else None,
        "template": _json_to_dict(request.template)
        if request.template is not None
        else None,
        "references": [_text_to_dict(item) for item in request.references],
    }


def _request_from_dict(value: Any) -> DomainPackRequest:
    data = _mapping(value, "Domain Pack request")
    style_value = data.get("style_profile")
    skill_value = data.get("skill")
    template_value = data.get("template")
    references_value = data.get("references", [])
    if not isinstance(references_value, list):
        raise DomainPackSnapshotError("references 必须是数组")
    run_context = _mapping(data.get("run_context"), "run_context")
    return DomainPackRequest(
        system_contract=_text_from_dict(data["system_contract"]),
        domain_contract=_text_from_dict(data["domain_contract"]),
        tool_contract=_json_from_dict(data["tool_contract"]),
        user_goal=_string(data.get("user_goal"), "user_goal"),
        run_context=run_context,
        style_profile=_style_from_dict(style_value)
        if style_value is not None
        else None,
        skill=_text_from_dict(skill_value) if skill_value is not None else None,
        template=_json_from_dict(template_value)
        if template_value is not None
        else None,
        references=tuple(_text_from_dict(item) for item in references_value),
    )


def _text_to_dict(document: VersionedText) -> dict[str, Any]:
    return {
        "source_id": document.source_id,
        "version": document.version,
        "content": document.content,
    }


def _text_from_dict(value: Any) -> VersionedText:
    data = _mapping(value, "文本来源")
    return VersionedText(
        source_id=_string(data.get("source_id"), "source_id"),
        version=_positive_int(data.get("version"), "version"),
        content=_string(data.get("content"), "content"),
    )


def _json_to_dict(document: VersionedJson) -> dict[str, Any]:
    return {
        "source_id": document.source_id,
        "version": document.version,
        "value": document.value,
    }


def _json_from_dict(value: Any) -> VersionedJson:
    data = _mapping(value, "JSON 来源")
    return VersionedJson(
        source_id=_string(data.get("source_id"), "source_id"),
        version=_positive_int(data.get("version"), "version"),
        value=data.get("value"),
    )


def _style_to_dict(profile: StyleProfile | None) -> dict[str, Any] | None:
    if profile is None:
        return None
    return {
        "profile_id": profile.profile_id,
        "version": profile.version,
        "scope": profile.scope,
        "confirmed": profile.confirmed,
        "preferences": profile.preferences,
        "avoid": list(profile.avoid),
    }


def _style_from_dict(value: Any) -> StyleProfile:
    data = _mapping(value, "StyleProfile")
    preferences = _mapping(data.get("preferences"), "StyleProfile.preferences")
    if not all(isinstance(key, str) and isinstance(item, str) for key, item in preferences.items()):
        raise DomainPackSnapshotError("StyleProfile preferences 必须是字符串映射")
    avoid = data.get("avoid", [])
    if not isinstance(avoid, list) or not all(isinstance(item, str) for item in avoid):
        raise DomainPackSnapshotError("StyleProfile avoid 必须是字符串数组")
    confirmed = data.get("confirmed")
    if not isinstance(confirmed, bool):
        raise DomainPackSnapshotError("StyleProfile confirmed 必须是布尔值")
    return StyleProfile(
        profile_id=_string(data.get("profile_id"), "profile_id"),
        version=_positive_int(data.get("version"), "version"),
        scope=_string(data.get("scope"), "scope"),
        confirmed=confirmed,
        preferences=dict(preferences),
        avoid=tuple(avoid),
    )


def _compiled_summary(compiled: CompiledDomainPack) -> dict[str, Any]:
    return {
        "content_hash": compiled.content_hash,
        "source_hashes": [
            {
                "source_id": source_id,
                "version": fingerprint.version,
                "content_hash": fingerprint.content_hash,
            }
            for source_id, fingerprint in compiled.source_hashes
        ],
        "omitted_sources": list(compiled.omitted_sources),
        "estimated_tokens": compiled.estimated_tokens,
    }


def _snapshot_hash(snapshot: Mapping[str, Any]) -> str:
    payload = dict(snapshot)
    payload.pop("snapshot_hash", None)
    encoded = _canonical_json(payload, "Domain Pack 快照")
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _constant_hash_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)


def _json_clone(value: Any, label: str) -> Any:
    return json.loads(_canonical_json(value, label))


def _canonical_json(value: Any, label: str) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise DomainPackSnapshotError(f"{label} 必须是合法 JSON 数据") from exc


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise DomainPackSnapshotError(f"{label} 必须是字符串键对象")
    return dict(value)


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise DomainPackSnapshotError(f"{label} 必须是字符串")
    return value


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise DomainPackSnapshotError(f"{label} 必须是正整数")
    return value
