"""LookLift 已支持 Harness 的内置声明式 Runtime 目录。"""
from __future__ import annotations

from .runtime_registry import RuntimeDefinition, RuntimeRegistry


_DEFINITIONS = (
    RuntimeDefinition(
        runtime_id="pydantic-api",
        kind="api",
        endpoint="provider://configured",
        input_transport="provider_message",
        stream_format="pydantic_events",
        capabilities=frozenset({"proxy_image", "structured_terminal"}),
        permission_profile=frozenset({"proxy_image", "structured_terminal"}),
    ),
    RuntimeDefinition(
        runtime_id="pi-cli",
        kind="cli",
        command="pi",
        input_transport="cli_workspace",
        stream_format="jsonl",
        capabilities=frozenset(
            {"proxy_image", "structured_terminal", "resume", "mcp"}
        ),
        permission_profile=frozenset(
            {"proxy_image", "structured_terminal", "resume", "mcp"}
        ),
        supports_resume=True,
        supports_mcp=True,
    ),
    RuntimeDefinition(
        runtime_id="fake",
        kind="fake",
        capabilities=frozenset({"proxy_image", "structured_terminal"}),
        permission_profile=frozenset({"proxy_image", "structured_terminal"}),
    ),
)


def builtin_runtime_registry() -> RuntimeRegistry:
    """返回独立 Registry，避免调用方修改全局状态。"""
    registry = RuntimeRegistry()
    for definition in _DEFINITIONS:
        registry.register(definition)
    return registry
