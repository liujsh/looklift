from __future__ import annotations

import pytest

from looklift.provider_snapshot import ProviderProtocol, ProviderSnapshot
from looklift.runtime_registry import (
    RuntimeDefinition,
    RuntimeDefinitionError,
    RuntimeSupportLevel,
)
from looklift.runtime_stream import RuntimeStreamParser
from looklift.agent_adapter import AgentEventKind, ScriptedAgentEvent


def test_runtime_definition_v2_freezes_declarative_harness_contract() -> None:
    definition = RuntimeDefinition(
        runtime_id="codex-cli",
        kind="cli",
        command="codex",
        capabilities=frozenset({"proxy_image", "structured_terminal"}),
        permission_profile=frozenset({"proxy_image", "structured_terminal"}),
        input_transport="cli_workspace",
        stream_format="jsonl",
        contract_version=2,
        display_name="Codex",
        version_probe="codex-version",
        model_probe="codex-models",
        event_parser="codex-json-events",
        support_level=RuntimeSupportLevel.EXPERIMENTAL,
        supports_cancel=True,
        supports_timeout=True,
    )

    assert definition.display_name == "Codex"
    assert definition.support_level is RuntimeSupportLevel.EXPERIMENTAL
    assert definition.event_parser == "codex-json-events"


@pytest.mark.parametrize("missing", ["display_name", "version_probe", "model_probe", "event_parser"])
def test_runtime_definition_v2_rejects_incomplete_declaration(missing: str) -> None:
    values = {
        "display_name": "Codex",
        "version_probe": "codex-version",
        "model_probe": "codex-models",
        "event_parser": "codex-json-events",
    }
    values[missing] = None

    with pytest.raises(RuntimeDefinitionError, match="v2"):
        RuntimeDefinition(
            runtime_id="codex-cli",
            kind="cli",
            command="codex",
            contract_version=2,
            **values,
        )


@pytest.mark.parametrize("stream_format", ["jsonl", "json_rpc", "rpc", "sse"])
def test_runtime_definition_v2_accepts_declared_stream_formats(
    stream_format: str,
) -> None:
    definition = RuntimeDefinition(
        runtime_id=f"runtime-{stream_format}",
        kind="cli",
        command="agent",
        stream_format=stream_format,
        contract_version=2,
        display_name="Agent",
        version_probe="agent-version",
        model_probe="agent-models",
        event_parser="agent-events",
    )

    assert definition.stream_format == stream_format


def test_runtime_definition_v1_remains_readable_during_migration() -> None:
    definition = RuntimeDefinition("legacy-api", "api", endpoint="provider://configured")

    assert definition.contract_version == 1
    assert definition.display_name == "legacy-api"


def test_provider_snapshot_is_versioned_and_never_contains_key_plaintext() -> None:
    snapshot = ProviderSnapshot(
        provider_id="openai",
        base_url="https://api.openai.com/v1",
        model="gpt-5",
        api_key_ref="credential://openai/default",
        protocol=ProviderProtocol.OPENAI_RESPONSES,
        max_tokens=4096,
        config_version=1,
    )

    assert snapshot.api_key_ref.startswith("credential://")
    assert not hasattr(snapshot, "api_key")


def test_ollama_snapshot_does_not_require_api_key_reference() -> None:
    snapshot = ProviderSnapshot(
        provider_id="ollama",
        base_url="http://127.0.0.1:11434/v1",
        model="qwen3-vl",
        api_key_ref=None,
        protocol=ProviderProtocol.OLLAMA_OPENAI_COMPATIBLE,
        max_tokens=4096,
        config_version=1,
    )

    assert snapshot.api_key_ref is None


def test_remote_provider_snapshot_requires_credential_reference() -> None:
    with pytest.raises(ValueError, match="凭据引用"):
        ProviderSnapshot(
            provider_id="openai",
            base_url="https://api.openai.com/v1",
            model="gpt-5",
            api_key_ref=None,
            protocol=ProviderProtocol.OPENAI_RESPONSES,
            max_tokens=4096,
            config_version=1,
        )


def test_runtime_stream_parser_has_transport_neutral_incremental_abi() -> None:
    class FakeParser:
        def feed(self, chunk: bytes) -> tuple[ScriptedAgentEvent, ...]:
            assert chunk == b"event"
            return (ScriptedAgentEvent(AgentEventKind.TEXT_DELTA, {"text": "分析中"}),)

        def finish(self) -> tuple[ScriptedAgentEvent, ...]:
            return ()

    parser = FakeParser()

    assert isinstance(parser, RuntimeStreamParser)
    assert parser.feed(b"event")[0].kind is AgentEventKind.TEXT_DELTA
