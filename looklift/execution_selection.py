"""执行模式 → Runtime 的无 CLI 选择算法（spec 8.1 / 需求 8、9）。

规则：`execution_mode=api` 时固定选择 API Runtime（`openai-api`），**无论本机
CLI 是否可用都不回退到 CLI、不探测、不安装、不启动任何 CLI**；只有 API Provider
配置缺失、凭据解析失败或 Provider 不受支持时才失败。`execution_mode=cli` 时选择
CLI Runtime。显式传入 `runtime_id` 时优先使用，但必须与执行模式匹配（api 模式只能
选 kind=api，cli 模式只能选 kind=cli），否则视为不一致并拒绝。
"""
from __future__ import annotations

from .runtime_registry import RuntimeDefinition, RuntimeDefinitionError, RuntimeRegistry

API_RUNTIME_ID = "openai-api"


class ExecutionSelectionError(ValueError):
    """执行选择无效、不一致或缺少必要配置。"""


def resolve_runtime_id(
    *,
    execution_mode: str,
    runtime_id: str | None,
    cli_available: bool,
    provider_configured: bool,
    registry: RuntimeRegistry,
) -> str:
    """解析本次执行使用的 Runtime ID。

    - `runtime_id` 显式给出：校验存在且与 `execution_mode` 的 kind 一致。
    - `runtime_id` 为空：按 `execution_mode` 选择；api 模式固定 `openai-api` 且
      要求 Provider 已配置，cli 模式要求至少一个 CLI 可用。
    - 任何不一致都抛 `ExecutionSelectionError`，不尝试 CLI fallback。
    """
    if execution_mode not in {"api", "cli"}:
        raise ExecutionSelectionError("execution_mode 必须是 api 或 cli")

    if runtime_id is not None:
        return _validate_explicit(
            runtime_id=runtime_id,
            execution_mode=execution_mode,
            registry=registry,
        )

    if execution_mode == "api":
        if not provider_configured:
            raise ExecutionSelectionError(
                "未保存 API Provider 配置，API 模式无法执行；请先在设置中配置"
            )
        return API_RUNTIME_ID

    # cli 模式：从可用且启用的 CLI 中选默认，没有则失败（不回退到 API）
    if not cli_available:
        raise ExecutionSelectionError("没有可用的本机 CLI，CLI 模式无法执行")
    return _default_cli_id(registry)


def _validate_explicit(*, runtime_id: str, execution_mode: str, registry: RuntimeRegistry) -> str:
    try:
        definition = registry.get(runtime_id)
    except RuntimeDefinitionError as exc:
        raise ExecutionSelectionError("未知 Runtime") from exc
    expected_kind = "api" if execution_mode == "api" else "cli"
    if definition.kind != expected_kind:
        raise ExecutionSelectionError(
            f"执行模式 {execution_mode} 与所选 Runtime（{runtime_id}，kind={definition.kind}）不一致"
        )
    return runtime_id


def _default_cli_id(registry: RuntimeRegistry) -> str:
    clis = [
        definition.runtime_id
        for definition in registry.list()
        if definition.kind == "cli"
    ]
    if not clis:
        raise ExecutionSelectionError("没有可用 CLI Runtime")
    # 优先 pi-cli（STABLE），其次按注册顺序
    for preferred in ("pi-cli", "claude-code", "codex-cli", "deepseek-cli"):
        if preferred in clis:
            return preferred
    return clis[0]


def cli_available_from_snapshot(
    detections: list[RuntimeDefinition],
    *,
    available: set[str],
    enabled: set[str],
) -> bool:
    """按探测结果与启用状态判断是否有可用 CLI（离线可测，无触网）。"""
    return any(
        definition.kind == "cli"
        and definition.runtime_id in available
        and definition.runtime_id in enabled
        for definition in detections
    )
