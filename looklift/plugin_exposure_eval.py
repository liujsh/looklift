"""插件工具暴露策略的确定性离线评估。"""

from __future__ import annotations

import json
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from .capabilities import CapabilityGrant
from .plugin_registry import PluginRegistry
from .plugin_tools import ExposureBudget, PluginTool, PluginToolCatalog, PluginToolError

TokenCounter = Callable[[str], int]


@dataclass(frozen=True)
class ExposureEvalReport:
    """只声明离线可证明的召回、契约和上下文成本。"""

    authorized_tool_count: int
    candidate_count: int
    full_catalog_tokens: int
    preselected_tokens: int
    progressive_tokens: int
    retrieval_hit: bool
    arguments_valid: bool
    offline_contract_passed: bool
    measurement_method: str
    elapsed_ms: float
    real_model_task_completion: Literal["pending_manual"] = "pending_manual"


def evaluate_exposure(
    registry: PluginRegistry,
    *,
    query: str,
    expected_identity: str,
    expected_arguments: Mapping[str, Any],
    project_id: str,
    grants: Sequence[CapabilityGrant],
    candidate_limit: int = 5,
    preselected_limit: int = 16,
    token_counter: TokenCounter | None = None,
) -> ExposureEvalReport:
    """对照全量、任务预选和渐进暴露，不调模型或真实插件。"""
    if not 1 <= candidate_limit <= 100 or not 1 <= preselected_limit <= 100:
        raise ValueError("评估候选上限必须介于 1 与 100")
    started = time.perf_counter()
    catalog = PluginToolCatalog(registry)
    authorized = _authorized_tools(
        registry,
        project_id=project_id,
        grants=grants,
    )
    candidates = catalog.discover(
        query,
        project_id=project_id,
        grants=grants,
        limit=candidate_limit,
    )
    preselected = catalog.discover(
        query,
        project_id=project_id,
        grants=grants,
        limit=preselected_limit,
    )
    retrieval_hit = any(item.identity == expected_identity for item in candidates.items)
    expected_tool = catalog.resolve(expected_identity)
    try:
        catalog.validate(expected_identity, expected_arguments)
    except PluginToolError:
        arguments_valid = False
    else:
        arguments_valid = True

    full_payload = [_tool_payload(tool) for tool in authorized]
    preselected_payload = [
        _tool_payload(catalog.resolve(item.identity)) for item in preselected.items
    ]
    summary_payload = [item.public_dict() for item in candidates.items]
    active_payload: list[dict[str, Any]] = []
    if retrieval_hit:
        active = catalog.activate(
            (expected_identity,),
            budget=ExposureBudget(
                max_schema_bytes=max(32 * 1024, _schema_bytes(expected_tool)),
                max_tools=1,
            ),
        )
        active_payload = [
            {
                "name": item.provider_name,
                "description": item.description,
                "input_schema": item.input_schema,
            }
            for item in active.tools
        ]

    def measure(value: Any) -> int:
        return _measure(value, token_counter=token_counter)

    return ExposureEvalReport(
        authorized_tool_count=len(authorized),
        candidate_count=len(candidates.items),
        full_catalog_tokens=measure(full_payload),
        preselected_tokens=measure(preselected_payload),
        progressive_tokens=measure(
            {"discovery": summary_payload, "activated": active_payload}
        ),
        retrieval_hit=retrieval_hit,
        arguments_valid=arguments_valid,
        offline_contract_passed=retrieval_hit and arguments_valid,
        measurement_method=(
            "provider_tokenizer" if token_counter is not None else "utf8_bytes_upper_bound"
        ),
        elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
    )


def _authorized_tools(
    registry: PluginRegistry,
    *,
    project_id: str,
    grants: Sequence[CapabilityGrant],
) -> tuple[PluginTool, ...]:
    authorized = {
        (grant.subject, grant.version_hash): grant
        for grant in grants
        if grant.project_id == project_id and grant.active()
    }
    return tuple(
        tool
        for tool in registry.all_tools()
        if (grant := authorized.get((tool.plugin_name, tool.plugin_hash))) is not None
        and tool.capabilities <= grant.capabilities
    )


def _tool_payload(tool: PluginTool) -> dict[str, Any]:
    return {
        "name": tool.identity,
        "description": tool.description,
        "input_schema": tool.input_schema,
    }


def _schema_bytes(tool: PluginTool) -> int:
    return len(
        json.dumps(
            tool.input_schema,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _measure(value: Any, *, token_counter: TokenCounter | None) -> int:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    if token_counter is None:
        return len(encoded.encode("utf-8"))
    measured = token_counter(encoded)
    if not isinstance(measured, int) or isinstance(measured, bool) or measured < 0:
        raise ValueError("Provider tokenizer 返回无效计量")
    return measured
