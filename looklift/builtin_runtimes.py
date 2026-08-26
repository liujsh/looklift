"""LookLift 已支持 Harness 的内置声明式 Runtime 目录。"""
from __future__ import annotations

from .runtime_registry import (
    RuntimeDefinition,
    RuntimeRegistry,
    RuntimeSupportLevel,
)


_DEFINITIONS = (
    RuntimeDefinition(
        runtime_id="claude-code",
        kind="cli",
        command="claude",
        capabilities=frozenset({"proxy_image", "structured_terminal", "mcp"}),
        permission_profile=frozenset(
            {"proxy_image", "structured_terminal", "mcp"}
        ),
        input_transport="cli_workspace",
        stream_format="jsonl",
        supports_mcp=True,
        contract_version=2,
        display_name="Claude Code",
        version_probe="claude-version",
        model_probe="claude-models",
        event_parser="claude-json-events",
    ),
    RuntimeDefinition(
        runtime_id="codex-cli",
        kind="cli",
        command="codex",
        capabilities=frozenset({"proxy_image", "structured_terminal", "mcp"}),
        permission_profile=frozenset(
            {"proxy_image", "structured_terminal", "mcp"}
        ),
        input_transport="cli_workspace",
        stream_format="jsonl",
        supports_mcp=True,
        contract_version=2,
        display_name="Codex",
        version_probe="codex-version",
        model_probe="codex-models",
        event_parser="codex-json-events",
    ),
    RuntimeDefinition(
        runtime_id="pi-cli",
        kind="cli",
        command="pi",
        input_transport="cli_workspace",
        stream_format="rpc",
        capabilities=frozenset(
            {"proxy_image", "structured_terminal", "resume", "mcp"}
        ),
        permission_profile=frozenset(
            {"proxy_image", "structured_terminal", "resume", "mcp"}
        ),
        supports_resume=True,
        supports_mcp=True,
        contract_version=2,
        display_name="Pi",
        version_probe="pi-version",
        model_probe="pi-models",
        event_parser="pi-rpc-events",
        support_level=RuntimeSupportLevel.STABLE,
    ),
    RuntimeDefinition(
        runtime_id="deepseek-cli",
        kind="cli",
        command="dsh",
        capabilities=frozenset({"proxy_image", "structured_terminal"}),
        permission_profile=frozenset({"proxy_image", "structured_terminal"}),
        input_transport="cli_workspace",
        stream_format="jsonl",
        contract_version=2,
        display_name="DeepSeek Harness",
        version_probe="deepseek-version",
        model_probe="deepseek-models",
        event_parser="deepseek-json-events",
    ),
    RuntimeDefinition(
        runtime_id="openai-api",
        kind="api",
        endpoint="provider://openai-configured",
        capabilities=frozenset({"proxy_image", "structured_terminal"}),
        permission_profile=frozenset({"proxy_image", "structured_terminal"}),
        input_transport="provider_message",
        stream_format="sse",
        contract_version=2,
        display_name="OpenAI API",
        version_probe="openai-api-version",
        model_probe="openai-models",
        event_parser="openai-sse-events",
    ),
    RuntimeDefinition(
        runtime_id="pydantic-api",
        kind="api",
        endpoint="provider://configured",
        input_transport="provider_message",
        stream_format="pydantic_events",
        capabilities=frozenset({"proxy_image", "structured_terminal"}),
        permission_profile=frozenset({"proxy_image", "structured_terminal"}),
        selectable=False,
    ),
    RuntimeDefinition(
        runtime_id="fake",
        kind="fake",
        capabilities=frozenset({"proxy_image", "structured_terminal"}),
        permission_profile=frozenset({"proxy_image", "structured_terminal"}),
        selectable=False,
    ),
)


def builtin_runtime_registry() -> RuntimeRegistry:
    """返回独立 Registry，避免调用方修改全局状态。"""
    registry = RuntimeRegistry()
    for definition in _DEFINITIONS:
        registry.register(definition)
    return registry
