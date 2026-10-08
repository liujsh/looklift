from __future__ import annotations

import pytest

from looklift.capabilities import CapabilityGrant
from looklift.plugin_registry import PluginManifest, PluginRegistry
from looklift.plugin_tools import (
    PluginConfirmationField,
    ExposureBudget,
    PluginTool,
    PluginToolCatalog,
    PluginToolError,
    PluginToolGateway,
)


def test_confirmation_field_must_reference_declared_top_level_argument():
    digest = "a" * 64

    with pytest.raises(PluginToolError, match="确认字段"):
        PluginTool(
            "redbook", "1.0.0", digest, "main", "publish", "发布",
            {"type": "object", "properties": {"title": {"type": "string"}}},
            frozenset({"social.publish"}), "external_write",
            confirmation_fields=(
                PluginConfirmationField("unknown", "未知", "text"),
            ),
        )


def _manifest(name: str, digest: str, *, aliases: tuple[str, ...] = ()) -> PluginManifest:
    return PluginManifest(
        2,
        name,
        "1.0.0",
        "connector",
        "social_publish",
        "sidecar",
        ("exported_assets", "text"),
        frozenset({"social.publish"}),
        digest,
        aliases=aliases,
        description=f"{name} 图文发布",
    )


def _tool(plugin: str, digest: str, *, description: str = "发布图文", risk: str = "external_write") -> PluginTool:
    return PluginTool(
        plugin_name=plugin,
        plugin_version="1.0.0",
        plugin_hash=digest,
        service="main",
        name="publish_content",
        description=description,
        aliases=("发帖", "发布笔记"),
        task_tags=("图文", "社交发布"),
        capabilities=frozenset({"social.publish"}),
        risk=risk,
        input_schema={
            "type": "object",
            "properties": {
                "title": {"type": "string", "maxLength": 20},
                "asset_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "minItems": 1,
                },
            },
            "required": ["title", "asset_ids"],
            "additionalProperties": False,
        },
    )


def test_registry_persists_manifest_and_tool_catalog(tmp_path):
    digest = "a" * 64
    registry = PluginRegistry(tmp_path)
    registry.install(_manifest("redbook", digest, aliases=("小红书",)), tools=(_tool("redbook", digest),))

    restored = PluginRegistry(tmp_path)
    assert restored.resolve("redbook").aliases == ("小红书",)
    assert restored.tools_for("redbook")[0].name == "publish_content"


def test_discovery_filters_project_grant_before_ranking_and_hides_schema(tmp_path):
    red_hash, other_hash = "a" * 64, "b" * 64
    registry = PluginRegistry(tmp_path)
    registry.install(_manifest("redbook", red_hash, aliases=("小红书",)), tools=(_tool("redbook", red_hash),))
    registry.install(_manifest("other", other_hash), tools=(_tool("other", other_hash, description="论坛发帖"),))
    catalog = PluginToolCatalog(registry)
    grants = (
        CapabilityGrant("redbook", frozenset({"social.publish"}), "project-a", red_hash),
        CapabilityGrant("other", frozenset({"social.publish"}), "project-b", other_hash),
    )

    page = catalog.discover("把照片发到小红书", project_id="project-a", grants=grants, limit=5)

    assert [item.plugin_name for item in page.items] == ["redbook"]
    assert "input_schema" not in page.items[0].public_dict()
    assert page.items[0].state == "discoverable"


def test_exposure_uses_unique_alias_and_refuses_to_truncate_schema(tmp_path):
    digest_a, digest_b = "a" * 64, "b" * 64
    registry = PluginRegistry(tmp_path)
    registry.install(_manifest("redbook", digest_a), tools=(_tool("redbook", digest_a),))
    registry.install(_manifest("forum", digest_b), tools=(_tool("forum", digest_b),))
    catalog = PluginToolCatalog(registry)
    identities = tuple(tool.identity for tool in registry.all_tools())

    active = catalog.activate(identities, budget=ExposureBudget(max_schema_bytes=20_000))

    assert len({item.provider_name for item in active.tools}) == 2
    assert all(item.input_schema["required"] == ["title", "asset_ids"] for item in active.tools)
    with pytest.raises(PluginToolError, match="预算"):
        catalog.activate((identities[0],), budget=ExposureBudget(max_schema_bytes=10))


def test_gateway_requires_activation_hash_and_valid_arguments(tmp_path):
    digest = "a" * 64
    registry = PluginRegistry(tmp_path)
    tool = _tool("redbook", digest, risk="read_only")
    registry.install(_manifest("redbook", digest), tools=(tool,))
    catalog = PluginToolCatalog(registry)
    grant = CapabilityGrant("redbook", frozenset({"social.publish"}), "project-a", digest)
    calls: list[dict] = []

    def execute(selected: PluginTool, arguments: dict) -> dict:
        calls.append(arguments)
        return {"ok": True, "tool": selected.name}

    gateway = PluginToolGateway(catalog, execute)
    with pytest.raises(PluginToolError, match="激活"):
        gateway.invoke(tool.identity, tool.schema_hash, {"title": "测试", "asset_ids": ["asset-1"]})

    gateway.activate((tool.identity,), project_id="project-a", grants=(grant,))
    with pytest.raises(PluginToolError, match="参数"):
        gateway.invoke(tool.identity, tool.schema_hash, {"title": "测试", "asset_ids": [], "path": "C:/secret.jpg"})
    with pytest.raises(PluginToolError, match="Schema"):
        gateway.invoke(tool.identity, "0" * 64, {"title": "测试", "asset_ids": ["asset-1"]})

    result = gateway.invoke(tool.identity, tool.schema_hash, {"title": "测试", "asset_ids": ["asset-1"]})
    assert result == {"ok": True, "tool": "publish_content"}
    assert calls == [{"title": "测试", "asset_ids": ["asset-1"]}]


def test_changed_schema_invalidates_previous_activation(tmp_path):
    digest = "a" * 64
    registry = PluginRegistry(tmp_path)
    original = _tool("redbook", digest)
    registry.install(_manifest("redbook", digest), tools=(original,))
    catalog = PluginToolCatalog(registry)
    grant = CapabilityGrant("redbook", frozenset({"social.publish"}), "project-a", digest)
    gateway = PluginToolGateway(catalog, lambda _tool, _args: {"ok": True})
    gateway.activate((original.identity,), project_id="project-a", grants=(grant,))

    changed = PluginTool(**{**original.as_storage_dict(), "description": "已经变更", "input_schema": {"type": "object"}})
    registry.replace_tools("redbook", "1.0.0", (changed,))

    with pytest.raises(PluginToolError, match="失效"):
        gateway.invoke(original.identity, original.schema_hash, {"title": "测试", "asset_ids": ["asset-1"]})


def test_gateway_enforces_composed_json_schema_constraints(tmp_path):
    digest = "a" * 64
    registry = PluginRegistry(tmp_path)
    tool = PluginTool(
        "redbook", "1.0.0", digest, "main", "choice", "组合参数",
        {
            "type": "object",
            "properties": {"value": {"oneOf": [{"type": "string"}, {"type": "null"}]}},
            "required": ["value"],
        },
        frozenset({"social.publish"}), "read_only",
    )
    registry.install(_manifest("redbook", digest), tools=(tool,))
    catalog = PluginToolCatalog(registry)
    gateway = PluginToolGateway(catalog, lambda _tool, _args: {"ok": True})
    grant = CapabilityGrant("redbook", frozenset({"social.publish"}), "project-a", digest)
    gateway.activate((tool.identity,), project_id="project-a", grants=(grant,))

    with pytest.raises(PluginToolError, match="参数"):
        gateway.invoke(tool.identity, tool.schema_hash, {"value": 3})
