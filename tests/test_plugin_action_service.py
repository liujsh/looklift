from __future__ import annotations

import pytest

from looklift.capabilities import CapabilityGrant, CapabilityGrantStore
from looklift.plugin_action_service import PluginActionService, PluginActionServiceError
from looklift.plugin_actions import ActionState, PluginActionStore
from looklift.plugin_registry import PluginManifest, PluginRegistry
from looklift.plugin_tools import PluginConfirmationField, PluginTool


class FakeConnectorService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str, str, str, dict]] = []

    def call_tool(
        self,
        *,
        plugin_name: str,
        plugin_version: str,
        service_name: str,
        tool_name: str,
        project_id: str,
        account_id: str,
        arguments: dict,
    ) -> dict:
        self.calls.append(
            (
                plugin_name,
                plugin_version,
                service_name,
                tool_name,
                f"{project_id}/{account_id}",
                arguments,
            )
        )
        return {"published": True}


def _service(tmp_path):
    digest = "a" * 64
    registry = PluginRegistry()
    tool = PluginTool(
        "notes",
        "1.0.0",
        digest,
        "main",
        "publish",
        "发布内容",
        {
            "type": "object",
            "properties": {"title": {"type": "string", "minLength": 1}},
            "required": ["title"],
            "additionalProperties": False,
        },
        frozenset({"notes.publish"}),
        "external_write",
        confirmation_fields=(
            PluginConfirmationField("title", "标题", "text"),
        ),
    )
    registry.install(
        PluginManifest(
            2,
            "notes",
            "1.0.0",
            "connector",
            "publish",
            "sidecar",
            ("text",),
            frozenset({"notes.publish"}),
            digest,
        ),
        tools=(tool,),
    )
    grants = CapabilityGrantStore()
    grants.put(
        CapabilityGrant(
            "notes", frozenset({"notes.publish"}), "project-a", digest
        )
    )
    actions = PluginActionStore(tmp_path / "actions")
    action = actions.prepare(
        project_id="project-a",
        plugin_identity=tool.identity,
        plugin_hash=digest,
        schema_hash=tool.schema_hash,
        account_id="account-a",
        arguments={"title": "初稿"},
        asset_hashes=("b" * 64,),
    )
    connectors = FakeConnectorService()
    return (
        PluginActionService(
            action_store=actions,
            plugin_registry=registry,
            grant_store=grants,
            connector_service=connectors,
        ),
        actions,
        action,
        connectors,
        registry,
    )


def test_action_service_projects_safely_and_executes_confirmed_revision(tmp_path):
    service, actions, action, connectors, _registry = _service(tmp_path)

    assert service.list(project_id="project-b") == ()
    projected = service.list(project_id="project-a")[0]
    assert projected["arguments"] == {"title": "初稿"}
    assert projected["asset_hashes"] == ["b" * 64]
    assert projected["confirmation_fields"] == [
        {
            "key": "title",
            "label": "标题",
            "control": "text",
            "options": [],
        }
    ]
    assert "plugin_hash" not in projected
    assert "schema_hash" not in projected
    assert "confirmation_hash" not in projected

    revised = service.revise(
        action.action_id,
        project_id="project-a",
        expected_revision=1,
        arguments={"title": "最终稿"},
    )
    assert revised["revision"] == 2
    with pytest.raises(PluginActionServiceError, match="revision"):
        service.confirm_and_execute(
            action.action_id,
            project_id="project-a",
            expected_revision=1,
        )

    result = service.confirm_and_execute(
        action.action_id,
        project_id="project-a",
        expected_revision=2,
    )

    assert result["state"] == ActionState.SUCCEEDED.value
    assert actions.get(action.action_id).confirmation_consumed is True
    assert connectors.calls == [
        ("notes", "1.0.0", "main", "publish", "project-a/account-a", {"title": "最终稿"})
    ]


def test_action_service_rejects_cross_project_invalid_edits_and_cancel(tmp_path):
    service, actions, action, connectors, _registry = _service(tmp_path)

    with pytest.raises(PluginActionServiceError, match="项目"):
        service.revise(
            action.action_id,
            project_id="project-b",
            expected_revision=1,
            arguments={"title": "越权"},
        )
    with pytest.raises(PluginActionServiceError, match="参数"):
        service.revise(
            action.action_id,
            project_id="project-a",
            expected_revision=1,
            arguments={"title": ""},
        )
    with pytest.raises(PluginActionServiceError, match="revision"):
        service.confirm_and_execute(
            action.action_id,
            project_id="project-a",
            expected_revision=True,
        )

    cancelled = service.cancel(action.action_id, project_id="project-a")

    assert cancelled["state"] == ActionState.CANCELLED.value
    assert actions.get(action.action_id).state is ActionState.CANCELLED
    assert connectors.calls == []


def test_disabled_plugin_keeps_action_history_readable_but_blocks_execution(tmp_path):
    service, _actions, action, connectors, registry = _service(tmp_path)
    registry.set_enabled("notes", "1.0.0", enabled=False)

    projected = service.list(project_id="project-a")[0]

    assert projected["action_id"] == action.action_id
    assert projected["confirmation_fields"] == []
    with pytest.raises(PluginActionServiceError, match="失效"):
        service.confirm_and_execute(
            action.action_id,
            project_id="project-a",
            expected_revision=1,
        )
    assert connectors.calls == []
