"""Domain Pack 快照与恢复契约。"""
from __future__ import annotations

import hashlib
import json

import pytest

from looklift.domain_pack import compile_domain_pack
from looklift.domain_pack_snapshot import (
    DomainPackSnapshotError,
    create_domain_pack_snapshot,
    restore_domain_pack_snapshot,
)
from looklift.domain_pack_types import (
    DomainPackRequest,
    StyleProfile,
    VersionedJson,
    VersionedText,
)


def _request() -> DomainPackRequest:
    return DomainPackRequest(
        system_contract=VersionedText("system", 1, "禁止正式提交。"),
        domain_contract=VersionedText("photo-editing", 2, "只生成白盒候选。"),
        tool_contract=VersionedJson(
            "tools", 1, {"tools": ["render_candidate", "finish_candidate"]}
        ),
        user_goal="自然提亮，保留高光。",
        run_context={"photo": "proxy", "analysis": {"basic": {"exposure": 0}}},
        style_profile=StyleProfile(
            profile_id="natural",
            version=3,
            scope="project",
            confirmed=True,
            preferences={"overall": "自然克制"},
            avoid=("过度饱和",),
        ),
        skill=VersionedText("portrait-natural", 4, "先观察主体和背景。"),
        template=VersionedJson(
            "portrait-look", 5, {"analysis_patch": {"basic": {"contrast": -5}}}
        ),
        references=(
            VersionedText("knowledge-light", 1, "曝光影响整体亮度。"),
            VersionedText("knowledge-color", 1, "色温影响冷暖倾向。"),
        ),
    )


def test_snapshot_round_trip_recompiles_to_identical_domain_pack():
    request = _request()
    expected = compile_domain_pack(request)

    snapshot = create_domain_pack_snapshot(request)
    restored = restore_domain_pack_snapshot(json.loads(json.dumps(snapshot)))

    assert restored.request == request
    assert restored.compiled == expected
    assert restored.max_prompt_chars is None
    assert snapshot["schema_version"] == 1
    assert len(snapshot["snapshot_hash"]) == 64


def test_snapshot_preserves_budget_and_omitted_references():
    request = _request()
    required = compile_domain_pack(
        DomainPackRequest(
            system_contract=request.system_contract,
            domain_contract=request.domain_contract,
            tool_contract=request.tool_contract,
            user_goal=request.user_goal,
            run_context=request.run_context,
            style_profile=request.style_profile,
            skill=request.skill,
            template=request.template,
        )
    )
    snapshot = create_domain_pack_snapshot(
        request,
        max_prompt_chars=len(required.instructions),
    )

    restored = restore_domain_pack_snapshot(snapshot)

    assert restored.max_prompt_chars == len(required.instructions)
    assert restored.compiled.omitted_sources == (
        "knowledge-light",
        "knowledge-color",
    )


def test_snapshot_rejects_content_changed_after_creation():
    snapshot = create_domain_pack_snapshot(_request())
    snapshot["request"]["domain_contract"]["content"] = "被替换的规则"

    with pytest.raises(DomainPackSnapshotError, match="完整性"):
        restore_domain_pack_snapshot(snapshot)


def test_snapshot_rejects_unknown_schema_version():
    snapshot = create_domain_pack_snapshot(_request())
    snapshot["schema_version"] = 99

    with pytest.raises(DomainPackSnapshotError, match="格式版本"):
        restore_domain_pack_snapshot(snapshot)


def test_snapshot_rejects_compiled_summary_that_no_longer_matches():
    snapshot = create_domain_pack_snapshot(_request())
    snapshot["compiled"]["content_hash"] = "0" * 64
    payload = dict(snapshot)
    payload.pop("snapshot_hash")
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )
    # 模拟迁移程序重算外层 Hash，但没有同步真实编译结果。
    snapshot["snapshot_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    with pytest.raises(DomainPackSnapshotError, match="编译摘要"):
        restore_domain_pack_snapshot(snapshot)


def test_snapshot_result_is_detached_from_mutable_input_data():
    run_context = {"nested": {"value": 1}}
    request = _request()
    request = DomainPackRequest(
        system_contract=request.system_contract,
        domain_contract=request.domain_contract,
        tool_contract=request.tool_contract,
        user_goal=request.user_goal,
        run_context=run_context,
    )
    snapshot = create_domain_pack_snapshot(request)

    run_context["nested"]["value"] = 999

    assert snapshot["request"]["run_context"]["nested"]["value"] == 1
