from __future__ import annotations

import pytest

from looklift.builtin_runtimes import builtin_runtime_registry
from looklift.execution_selection import (
    ExecutionSelectionError,
    cli_available_from_snapshot,
    resolve_runtime_id,
)


def _registry():
    return builtin_runtime_registry()


def test_api_mode_selects_openai_api_even_without_cli():
    rid = resolve_runtime_id(
        execution_mode="api",
        runtime_id=None,
        cli_available=False,  # 无 CLI 不是错误
        provider_configured=True,
        registry=_registry(),
    )
    assert rid == "openai-api"


def test_api_mode_fails_when_provider_not_configured_no_cli_fallback():
    with pytest.raises(ExecutionSelectionError, match="Provider 配置"):
        resolve_runtime_id(
            execution_mode="api",
            runtime_id=None,
            cli_available=True,  # 即使有 CLI 也不回退
            provider_configured=False,
            registry=_registry(),
        )


def test_cli_mode_fails_when_no_cli_available():
    with pytest.raises(ExecutionSelectionError, match="本机 CLI"):
        resolve_runtime_id(
            execution_mode="cli",
            runtime_id=None,
            cli_available=False,
            provider_configured=True,
            registry=_registry(),
        )


def test_cli_mode_selects_default_cli():
    rid = resolve_runtime_id(
        execution_mode="cli",
        runtime_id=None,
        cli_available=True,
        provider_configured=True,
        registry=_registry(),
    )
    assert rid in {"pi-cli", "claude-code", "codex-cli", "deepseek-cli"}


def test_explicit_runtime_must_match_mode():
    # api 模式显式传 CLI runtime -> 拒绝，不回退
    with pytest.raises(ExecutionSelectionError, match="不一致"):
        resolve_runtime_id(
            execution_mode="api",
            runtime_id="claude-code",
            cli_available=True,
            provider_configured=True,
            registry=_registry(),
        )
    # cli 模式显式传 api runtime -> 拒绝
    with pytest.raises(ExecutionSelectionError, match="不一致"):
        resolve_runtime_id(
            execution_mode="cli",
            runtime_id="openai-api",
            cli_available=True,
            provider_configured=True,
            registry=_registry(),
        )


def test_explicit_api_runtime_passes_in_api_mode():
    rid = resolve_runtime_id(
        execution_mode="api",
        runtime_id="openai-api",
        cli_available=False,
        provider_configured=True,
        registry=_registry(),
    )
    assert rid == "openai-api"


def test_unknown_runtime_rejected():
    with pytest.raises(ExecutionSelectionError, match="未知 Runtime"):
        resolve_runtime_id(
            execution_mode="api",
            runtime_id="does-not-exist",
            cli_available=False,
            provider_configured=True,
            registry=_registry(),
        )


def test_invalid_mode_rejected():
    with pytest.raises(ExecutionSelectionError, match="execution_mode"):
        resolve_runtime_id(
            execution_mode="hybrid",
            runtime_id=None,
            cli_available=True,
            provider_configured=True,
            registry=_registry(),
        )


def test_cli_available_from_snapshot_requires_available_and_enabled():
    definitions = list(builtin_runtime_registry().list())
    assert cli_available_from_snapshot(
        definitions,
        available={"pi-cli", "openai-api"},
        enabled={"pi-cli", "openai-api"},
    ) is True
    # CLI 存在但未启用 -> 不可用
    assert cli_available_from_snapshot(
        definitions,
        available={"pi-cli"},
        enabled=set(),
    ) is False
    # 只有 API runtime 可用 -> 不可用（无 CLI）
    assert cli_available_from_snapshot(
        definitions,
        available={"openai-api"},
        enabled={"openai-api"},
    ) is False
