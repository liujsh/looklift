import pytest

from looklift.capabilities import CapabilityGrant, effective_capabilities, require_capability
from looklift.proposal import ProposalError, ProposalService
from looklift.run_manifest import RunManifestStore, hash_text
from looklift.agent_adapter import AgentEvent, AgentEventKind
from looklift.runtime_registry import (
    RuntimeDefinition,
    RuntimeDefinitionError,
    RuntimeDetectionEngine,
    RuntimeRegistry,
)
from looklift.context_memory import ContextEntry, ContextMemoryStore
from looklift.plugin_registry import PluginManifest, PluginManifestError, PluginRegistry
from looklift.connector import make_source_packet, validate_external_url


def test_proposal_has_single_confirm_apply_lifecycle_and_conflict():
    service = ProposalService()
    item = service.preview(target_type="ProjectContext", target_id="p", base_hash="a", patch={"x": 1})
    with pytest.raises(ProposalError):
        service.apply(item.proposal_id, current_hash="a", apply_target=lambda _: "r")
    service.confirm(item.proposal_id)
    conflict = service.apply(item.proposal_id, current_hash="b", apply_target=lambda _: "r")
    assert conflict.status == "conflict"


def test_capability_is_intersection_and_revocation_is_immediate():
    grant = CapabilityGrant("plugin", frozenset({"workspace.read_metadata", "network.read"}), "p", "h")
    assert effective_capabilities(grant, {"workspace.read_metadata"}, {"workspace.read_metadata"}) == {"workspace.read_metadata"}
    with pytest.raises(PermissionError):
        require_capability("network.read", grant=grant, permission_profile={"network.read"}, tool_contract=set())


def test_runtime_registry_validates_api_cli_fake_shapes():
    registry = RuntimeRegistry()
    registry.register(RuntimeDefinition("fake", "fake", capabilities=frozenset({"candidate"}), permission_profile=frozenset()))
    with pytest.raises(RuntimeDefinitionError):
        RuntimeDefinition("bad", "api")
    assert registry.get("fake").kind == "fake"


def test_runtime_definition_declares_transport_and_detection_is_isolated():
    async def exercise():
        registry = RuntimeRegistry()
        registry.register(
            RuntimeDefinition(
                "api",
                "api",
                endpoint="https://provider.invalid",
                input_transport="provider_message",
                stream_format="pydantic_events",
                capabilities=frozenset({"proxy_image"}),
            )
        )
        registry.register(RuntimeDefinition("fake", "fake"))

        async def available(_definition):
            return {"version": "1", "authenticated": True, "models": ("m",)}

        async def broken(_definition):
            raise RuntimeError("secret-token")

        results = await RuntimeDetectionEngine(
            registry,
            probes={"api": available, "fake": broken},
        ).detect_all()
        assert results[0].available is True
        assert results[1].available is False
        assert "secret-token" not in (results[1].error or "")

    import asyncio

    asyncio.run(exercise())


def test_manifest_reconcile_and_attempt(tmp_path):
    store = RunManifestStore(tmp_path / "run.jsonl")
    baseline = hash_text("baseline")
    photo = hash_text("photo")
    manifest = store.create("run", baseline_hash=baseline, photo_hash=photo, attempt_id="a1")
    manifest = store.append(manifest, event_id="e1", sequence=1, kind="run_started", payload={})
    assert manifest.status == "running"
    interrupted = store.reconcile(manifest, baseline_hash=baseline)
    assert interrupted.status == "interrupted"
    resumed = store.start_attempt(interrupted, "a2")
    assert resumed.attempt_id == "a2"
    stale = store.reconcile(resumed, baseline_hash=hash_text("new"))
    assert stale.status == "stale"


def test_manifest_appends_normalized_agent_events_and_resets_attempt_sequence(tmp_path):
    store = RunManifestStore(tmp_path / "run.jsonl")
    baseline = hash_text("baseline")
    manifest = store.create("run", baseline_hash=baseline, photo_hash=hash_text("photo"), attempt_id="a1")
    started = AgentEvent(AgentEventKind.RUN_STARTED, "run", "a1", 1, {})
    manifest = store.append_agent_event(manifest, started)
    assert manifest.status == "running"
    manifest = store.reconcile(manifest, baseline_hash=baseline)
    manifest = store.start_attempt(manifest, "a2")
    assert manifest.last_sequence == 0
    manifest = store.append_agent_event(
        manifest, AgentEvent(AgentEventKind.RUN_STARTED, "run", "a2", 1, {})
    )
    assert manifest.last_sequence == 1


def test_context_memory_proposal_remains_optional_audit_path(tmp_path):
    store = ContextMemoryStore(tmp_path)
    entry = store.put(ContextEntry("fact-a", "fact", "原始事实", "user", state="active"))
    proposal = store.proposal(target_id="fact-a", content="更新事实", base_hash=entry.content_hash)
    store.proposals.confirm(proposal.proposal_id)
    applied = store.apply_proposal(proposal.proposal_id)
    assert applied.status == "applied"
    assert store.get("fact-a").content == "更新事实"


def test_disabled_context_never_enters_compiler_snapshot(tmp_path):
    store = ContextMemoryStore(tmp_path)
    store.put(ContextEntry("fact-active", "fact", "已激活", "user", state="active"))
    store.put(ContextEntry("fact-disabled", "fact", "已停用", "connector", state="disabled"))

    assert [entry.entry_id for entry in store.snapshot()] == ["fact-active"]


def test_plugin_manifest_and_connector_boundaries():
    registry = PluginRegistry()
    manifest = PluginManifest(1, "demo", "1.0.0", "connector", "catalog", "declarative", (), frozenset({"workspace.read_metadata"}), "a" * 64)
    registry.install(manifest)
    assert registry.resolve("demo").content_hash == "a" * 64
    with pytest.raises(PluginManifestError):
        PluginManifest(1, "bad", "1.0.0", "connector", "x", "declarative", (), frozenset({"shell.exec"}), "a" * 64)
    packet = make_source_packet("p1", "catalog", {"x": 1})
    assert len(packet.content_hash) == 64
    validate_external_url("https://example.com", resolved_ips=("93.184.216.34",))
    with pytest.raises(ValueError):
        validate_external_url("http://127.0.0.1", resolved_ips=("127.0.0.1",))
