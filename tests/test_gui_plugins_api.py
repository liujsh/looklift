from __future__ import annotations

import json

from looklift.gui import api
from looklift.capabilities import CapabilityGrantStore
from looklift.plugin_registry import PluginManifest, PluginRegistry
from looklift.plugin_tools import PluginTool


def _ctx(body=None, plugin_id="catalog-tools"):
    return {
        "params": {"id": plugin_id},
        "body": json.dumps(body).encode() if body is not None else None,
        "content_type": "application/json",
        "query": {},
    }


def test_plugin_api_lists_declared_capabilities_and_grants_subset():
    _, grants = api._plugin_stores()
    grants.clear()
    status, payload = api.ROUTES[("GET", "/api/plugins")]({"query": {"project_id": "project-a"}})
    assert status == 200
    plugin = next(item for item in payload["plugins"] if item["id"] == "catalog-tools")
    assert plugin["capabilities"] == ["connector.read_catalog"]
    assert plugin["granted_capabilities"] == []

    status, granted = api.ROUTES[("POST", "/api/plugins/<id>/grant")](
        _ctx({"project_id": "project-a", "capabilities": ["connector.read_catalog"], "scope": "run"})
    )
    assert status == 200
    assert granted["granted_capabilities"] == ["connector.read_catalog"]

    status, payload = api.ROUTES[("GET", "/api/plugins")]({"query": {"project_id": "project-a"}})
    assert payload["plugins"][0]["granted_capabilities"] == ["connector.read_catalog"]

    status, other = api.ROUTES[("GET", "/api/plugins")]({"query": {"project_id": "project-b"}})
    assert status == 200
    assert other["plugins"][0]["granted_capabilities"] == []


def test_plugin_api_rejects_capability_escalation_and_revokes():
    _, grants = api._plugin_stores()
    grants.clear()
    status, body = api.ROUTES[("POST", "/api/plugins/<id>/grant")](
        _ctx({"project_id": "project-a", "capabilities": ["shell.exec"], "scope": "run"})
    )
    assert status == 400
    assert "声明" in body["error"]

    api.ROUTES[("POST", "/api/plugins/<id>/grant")](
        _ctx({"project_id": "project-b", "capabilities": ["connector.read_catalog"], "scope": "attempt"})
    )
    status, revoked = api.ROUTES[("DELETE", "/api/plugins/<id>/grant")](
        {**_ctx(), "query": {"project_id": "project-b"}}
    )
    assert status == 200
    assert revoked["granted_capabilities"] == []


def test_plugin_api_restores_registry_and_grant_after_process_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(api.config, "CONFIG_PATH", tmp_path / "profile" / "config.toml")
    monkeypatch.setattr(api, "_PLUGIN_REGISTRY", None)
    monkeypatch.setattr(api, "_PLUGIN_GRANTS", None)
    monkeypatch.setattr(api, "_PLUGIN_STATE_ROOT", None)

    status, _ = api.ROUTES[("POST", "/api/plugins/<id>/grant")](
        _ctx({
            "project_id": "project-a",
            "capabilities": ["connector.read_catalog"],
            "scope": "run",
        })
    )
    assert status == 200

    monkeypatch.setattr(api, "_PLUGIN_REGISTRY", None)
    monkeypatch.setattr(api, "_PLUGIN_GRANTS", None)
    monkeypatch.setattr(api, "_PLUGIN_STATE_ROOT", None)
    status, payload = api.ROUTES[("GET", "/api/plugins")](
        {"query": {"project_id": "project-a"}}
    )

    assert status == 200
    assert payload["plugins"][0]["granted_capabilities"] == [
        "connector.read_catalog"
    ]
    assert (tmp_path / "profile" / "plugins" / "registry.json").is_file()
    assert (tmp_path / "profile" / "plugin-grants" / "grants.json").is_file()


def test_plugin_api_seeds_builtin_when_persisted_registry_has_other_plugin(
    tmp_path, monkeypatch
):
    profile = tmp_path / "profile"
    registry = PluginRegistry(profile / "plugins")
    registry.install(
        PluginManifest(
            2,
            "notes",
            "1.0.0",
            "connector",
            "notes",
            "sidecar",
            ("text",),
            frozenset({"notes.read"}),
            "b" * 64,
        )
    )
    monkeypatch.setattr(api.config, "CONFIG_PATH", profile / "config.toml")
    monkeypatch.setattr(api, "_PLUGIN_REGISTRY", None)
    monkeypatch.setattr(api, "_PLUGIN_GRANTS", None)
    monkeypatch.setattr(api, "_PLUGIN_STATE_ROOT", None)

    status, payload = api.ROUTES[("GET", "/api/plugins")]({"query": {}})

    assert status == 200
    assert {item["id"] for item in payload["plugins"]} == {
        "catalog-tools",
        "notes",
    }


def test_plugin_api_discovers_summary_then_describes_full_schema(monkeypatch):
    digest = "b" * 64
    registry = PluginRegistry()
    registry.install(
        PluginManifest(
            2, "redbook", "1.0.0", "connector", "publish", "sidecar", ("exported_assets",),
            frozenset({"social.publish"}), digest, aliases=("小红书",),
        ),
        tools=(
            PluginTool(
                "redbook", "1.0.0", digest, "main", "publish", "发布图文",
                {"type": "object", "properties": {"title": {"type": "string"}}},
                frozenset({"social.publish"}), "external_write",
            ),
        ),
    )
    grants = CapabilityGrantStore()
    monkeypatch.setattr(api, "_plugin_stores", lambda: (registry, grants))
    grants.put(
        api.CapabilityGrant("redbook", frozenset({"social.publish"}), "project-a", digest)
    )

    status, found = api.ROUTES[("POST", "/api/plugins/tools/discover")](
        _ctx({"project_id": "project-a", "query": "发到小红书"})
    )
    assert status == 200
    assert "input_schema" not in found["tools"][0]

    identity = found["tools"][0]["identity"]
    status, described = api.ROUTES[("POST", "/api/plugins/tools/describe")](
        _ctx({"project_id": "project-a", "identities": [identity]})
    )
    assert status == 200
    assert described["tools"][0]["input_schema"]["type"] == "object"

    status, denied = api.ROUTES[("POST", "/api/plugins/tools/describe")](
        _ctx({"project_id": "project-b", "identities": [identity]})
    )
    assert status == 403
    assert "授权" in denied["error"]
