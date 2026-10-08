from __future__ import annotations

from looklift.capabilities import CapabilityGrant
from looklift.plugin_exposure_eval import evaluate_exposure
from looklift.plugin_registry import PluginManifest, PluginRegistry
from looklift.plugin_tools import PluginTool


def _catalog(size: int) -> tuple[PluginRegistry, CapabilityGrant, str]:
    digest = "a" * 64
    manifest = PluginManifest(
        2,
        "synthetic",
        "1.0.0",
        "connector",
        "social_publish",
        "sidecar",
        ("text",),
        frozenset({"social.publish"}),
        digest,
        aliases=("合成平台",),
    )
    tools = tuple(
        PluginTool(
            "synthetic",
            "1.0.0",
            digest,
            "main",
            f"tool_{index:04d}",
            "发布目标图文" if index == size - 1 else f"普通备选工具 {index}",
            {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "maxLength": 40},
                    "ordinal": {"type": "integer", "const": index},
                },
                "required": ["title", "ordinal"],
                "additionalProperties": False,
            },
            frozenset({"social.publish"}),
            "read_only",
            aliases=("目标发布",) if index == size - 1 else (),
            task_tags=("图文",),
        )
        for index in range(size)
    )
    registry = PluginRegistry()
    registry.install(manifest, tools=tools)
    expected = tools[-1]
    grant = CapabilityGrant(
        "synthetic",
        frozenset({"social.publish"}),
        "project-a",
        digest,
    )
    return registry, grant, expected.identity


def test_exposure_eval_compares_10_100_1000_tool_catalogs_without_network():
    reports = []
    for size in (10, 100, 1000):
        registry, grant, expected = _catalog(size)
        reports.append(
            evaluate_exposure(
                registry,
                query="图文目标发布",
                expected_identity=expected,
                expected_arguments={"title": "测试", "ordinal": size - 1},
                project_id="project-a",
                grants=(grant,),
                candidate_limit=5,
            )
        )

    assert [report.authorized_tool_count for report in reports] == [10, 100, 1000]
    assert all(report.retrieval_hit for report in reports)
    assert all(report.arguments_valid for report in reports)
    assert all(report.offline_contract_passed for report in reports)
    assert all(report.real_model_task_completion == "pending_manual" for report in reports)
    assert [report.full_catalog_tokens for report in reports] == sorted(
        report.full_catalog_tokens for report in reports
    )
    assert all(report.progressive_tokens < report.preselected_tokens for report in reports)
    assert all(report.preselected_tokens <= report.full_catalog_tokens for report in reports)
    assert all(
        report.preselected_tokens < report.full_catalog_tokens for report in reports[1:]
    )
    assert all(report.elapsed_ms >= 0 for report in reports)


def test_exposure_eval_records_no_hit_and_invalid_arguments_without_claiming_completion():
    registry, grant, expected = _catalog(10)

    report = evaluate_exposure(
        registry,
        query="完全无关的需求",
        expected_identity=expected,
        expected_arguments={"title": "测试", "ordinal": -1},
        project_id="project-a",
        grants=(grant,),
        candidate_limit=5,
    )

    assert report.retrieval_hit is False
    assert report.arguments_valid is False
    assert report.offline_contract_passed is False
    assert report.real_model_task_completion == "pending_manual"


def test_exposure_eval_uses_injected_token_counter_and_reports_method():
    registry, grant, expected = _catalog(10)

    report = evaluate_exposure(
        registry,
        query="图文目标发布",
        expected_identity=expected,
        expected_arguments={"title": "测试", "ordinal": 9},
        project_id="project-a",
        grants=(grant,),
        token_counter=lambda value: len(value) // 8 + 1,
    )

    assert report.measurement_method == "provider_tokenizer"
