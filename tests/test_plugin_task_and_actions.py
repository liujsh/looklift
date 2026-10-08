from __future__ import annotations

from dataclasses import replace

import pytest

from looklift.agent_adapter import AgentImage, AgentRunInput, AgentTaskKind
from looklift.domain_pack_types import CompiledDomainPack
from looklift.plugin_actions import ActionError, ActionState, PluginActionStore
from looklift.capabilities import CapabilityGrant
from looklift.plugin_registry import PluginManifest, PluginRegistry
from looklift.plugin_tools import PluginTool, PluginToolCatalog, PluginToolError, PluginToolGateway


def _pack() -> CompiledDomainPack:
    return CompiledDomainPack("规则", "发到社交平台", (), (), "a" * 64, 8)


def test_plugin_task_supports_text_only_or_multiple_safe_images():
    text_only = AgentRunInput(
        "run-1", "attempt-1", _pack(), None, "model", task_kind=AgentTaskKind.PLUGIN_TASK
    )
    assert text_only.proxy_images == ()

    image_a = AgentImage("image/jpeg", b"jpeg-a")
    image_b = AgentImage("image/jpeg", b"jpeg-b")
    multi = replace(text_only, proxy_image=image_a, additional_proxy_images=(image_b,))
    assert multi.proxy_images == (image_a, image_b)

    with pytest.raises(ValueError, match="代理图"):
        AgentRunInput("run-2", "attempt-2", _pack(), None, "model")


def test_action_waits_for_confirmation_and_consumes_once(tmp_path):
    store = PluginActionStore(tmp_path)
    action = store.prepare(
        project_id="project-a",
        plugin_identity="redbook@1.0.0/main/publish_content",
        plugin_hash="a" * 64,
        schema_hash="b" * 64,
        account_id="account-a",
        arguments={"title": "秋日", "asset_ids": ["asset-1"]},
        asset_hashes=("c" * 64,),
    )
    assert action.state is ActionState.PENDING_CONFIRMATION
    with pytest.raises(ActionError, match="确认"):
        store.begin_execution(action.action_id)

    confirmed = store.confirm(action.action_id, expected_revision=1)
    executing = store.begin_execution(confirmed.action_id)
    assert executing.state is ActionState.EXECUTING
    with pytest.raises(ActionError, match="消费"):
        store.begin_execution(confirmed.action_id)

    restored = PluginActionStore(tmp_path).get(action.action_id)
    assert restored.state is ActionState.UNKNOWN
    assert restored.result["reason"] == "host_restarted"


def test_action_revision_change_invalidates_old_confirmation(tmp_path):
    store = PluginActionStore(tmp_path)
    action = store.prepare(
        project_id="project-a",
        plugin_identity="redbook@1.0.0/main/publish_content",
        plugin_hash="a" * 64,
        schema_hash="b" * 64,
        account_id="account-a",
        arguments={"title": "旧标题"},
        asset_hashes=("c" * 64,),
    )
    store.confirm(action.action_id, expected_revision=1)
    changed = store.revise(action.action_id, arguments={"title": "新标题"})

    assert changed.state is ActionState.PENDING_CONFIRMATION
    assert changed.revision == 2
    with pytest.raises(ActionError, match="revision"):
        store.confirm(action.action_id, expected_revision=1)


def test_action_expiry_and_cancellation_are_persisted(tmp_path):
    clock = [100.0]
    store = PluginActionStore(tmp_path, clock=lambda: clock[0])
    action = store.prepare(
        project_id="project-a",
        plugin_identity="redbook@1.0.0/main/publish_content",
        plugin_hash="a" * 64,
        schema_hash="b" * 64,
        account_id="account-a",
        arguments={},
        asset_hashes=(),
        ttl_seconds=10,
    )
    clock[0] = 111.0
    with pytest.raises(ActionError, match="过期"):
        store.confirm(action.action_id, expected_revision=1)
    assert store.get(action.action_id).state is ActionState.EXPIRED

    other = store.prepare(
        project_id="project-a",
        plugin_identity="redbook@1.0.0/main/publish_content",
        plugin_hash="a" * 64,
        schema_hash="b" * 64,
        account_id="account-a",
        arguments={},
        asset_hashes=(),
    )
    cancelled = store.cancel(other.action_id)
    assert cancelled.state is ActionState.CANCELLED


def test_action_marks_uncertain_write_without_automatic_retry(tmp_path):
    store = PluginActionStore(tmp_path)
    action = store.prepare(
        project_id="project-a",
        plugin_identity="redbook@1.0.0/main/publish_content",
        plugin_hash="a" * 64,
        schema_hash="b" * 64,
        account_id="account-a",
        arguments={"title": "测试"},
        asset_hashes=("c" * 64,),
    )
    store.confirm(action.action_id, expected_revision=1)
    store.begin_execution(action.action_id)
    uncertain = store.finish(action.action_id, state=ActionState.UNKNOWN, result={"message": "连接中断"})

    assert uncertain.state is ActionState.UNKNOWN
    with pytest.raises(ActionError, match="终态"):
        store.begin_execution(action.action_id)


def test_external_write_gateway_only_executes_after_host_confirmation(tmp_path):
    digest = "a" * 64
    manifest = PluginManifest(
        2, "redbook", "1.0.0", "connector", "publish", "sidecar", ("exported_assets",),
        frozenset({"social.publish"}), digest,
    )
    tool = PluginTool(
        "redbook", "1.0.0", digest, "main", "publish", "发布", {"type": "object"},
        frozenset({"social.publish"}), "external_write",
    )
    registry = PluginRegistry()
    registry.install(manifest, tools=(tool,))
    actions = PluginActionStore(tmp_path)
    calls = []
    gateway = PluginToolGateway(PluginToolCatalog(registry), lambda _tool, args: calls.append(args) or {"ok": True}, action_store=actions)
    grant = CapabilityGrant("redbook", frozenset({"social.publish"}), "project-a", digest)
    gateway.activate(
        (tool.identity,), project_id="project-a", grants=(grant,), account_id="account-a", asset_hashes=("c" * 64,)
    )

    pending = gateway.invoke(tool.identity, tool.schema_hash, {})
    assert pending["status"] == "pending_confirmation"
    assert calls == []

    action = actions.get(pending["action_id"])
    actions.confirm(action.action_id, expected_revision=action.revision)
    completed = gateway.execute_action(
        action.action_id, grants=(grant,), current_account_id="account-a"
    )
    assert completed["status"] == "succeeded"
    assert calls == [{}]

    revoked = replace(grant, revoked=True)
    second = gateway.invoke(tool.identity, tool.schema_hash, {})
    second_action = actions.get(second["action_id"])
    actions.confirm(second_action.action_id, expected_revision=1)
    with pytest.raises(PluginToolError, match="授权"):
        gateway.execute_action(
            second_action.action_id, grants=(revoked,), current_account_id="account-a"
        )
