from __future__ import annotations

import json

from looklift.gui import api


def _ctx(body=None, plugin_id="catalog-tools"):
    return {
        "params": {"id": plugin_id},
        "body": json.dumps(body).encode() if body is not None else None,
        "content_type": "application/json",
        "query": {},
    }


def test_plugin_api_lists_declared_capabilities_and_grants_subset():
    api._PLUGIN_GRANTS.clear()
    status, payload = api.ROUTES[("GET", "/api/plugins")]({})
    assert status == 200
    plugin = next(item for item in payload["plugins"] if item["id"] == "catalog-tools")
    assert plugin["capabilities"] == ["connector.read_catalog"]
    assert plugin["granted_capabilities"] == []

    status, granted = api.ROUTES[("POST", "/api/plugins/<id>/grant")](
        _ctx({"project_id": "project-a", "capabilities": ["connector.read_catalog"], "scope": "run"})
    )
    assert status == 200
    assert granted["granted_capabilities"] == ["connector.read_catalog"]

    status, payload = api.ROUTES[("GET", "/api/plugins")]({})
    assert payload["plugins"][0]["granted_capabilities"] == ["connector.read_catalog"]


def test_plugin_api_rejects_capability_escalation_and_revokes():
    api._PLUGIN_GRANTS.clear()
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
