from __future__ import annotations

import json

from looklift.gui import api


class FakeConnectorService:
    def __init__(self):
        self.calls = []

    def create(self, **payload):
        self.calls.append(("create", payload))
        return {"connector_id": "pc-1", "connected": False}

    def list(self, *, project_id):
        self.calls.append(("list", project_id))
        return ({"connector_id": "pc-1"},)

    def connect(self, connector_id, *, project_id):
        self.calls.append(("connect", connector_id, project_id))
        return {"connector_id": connector_id, "connected": True, "tools": 2}

    def disconnect(self, connector_id, *, project_id):
        self.calls.append(("disconnect", connector_id, project_id))
        return {"connector_id": connector_id, "connected": False}

    def forget(self, connector_id, *, project_id):
        self.calls.append(("forget", connector_id, project_id))
        return {"connector_id": connector_id, "authorized": False}


def _ctx(*, body=None, connector_id="pc-1", project_id=None):
    return {
        "params": {"id": connector_id},
        "body": json.dumps(body).encode() if body is not None else None,
        "content_type": "application/json",
        "query": {} if project_id is None else {"project_id": project_id},
    }


def test_plugin_connector_routes_create_list_connect_disconnect_and_forget(monkeypatch):
    service = FakeConnectorService()
    monkeypatch.setattr(api, "_PLUGIN_CONNECTOR_SERVICE", service)
    create = {
        "plugin_name": "notes",
        "version": "1.0.0",
        "service_name": "main",
        "project_id": "project-a",
        "account_id": "account-main",
        "credential": "secret",
        "confirmed": True,
    }

    assert api.ROUTES[("POST", "/api/plugin-connectors")](_ctx(body=create))[0] == 201
    assert api.ROUTES[("GET", "/api/plugin-connectors")](_ctx(project_id="project-a"))[0] == 200
    assert api.ROUTES[("POST", "/api/plugin-connectors/<id>/connect")](
        _ctx(body={"project_id": "project-a"})
    )[1]["tools"] == 2
    assert api.ROUTES[("DELETE", "/api/plugin-connectors/<id>/connection")](
        _ctx(project_id="project-a")
    )[1]["connected"] is False
    assert api.ROUTES[("DELETE", "/api/plugin-connectors/<id>/account")](
        _ctx(project_id="project-a")
    )[1]["authorized"] is False


def test_plugin_connector_create_rejects_command_injection_fields(monkeypatch):
    service = FakeConnectorService()
    monkeypatch.setattr(api, "_PLUGIN_CONNECTOR_SERVICE", service)
    status, body = api.ROUTES[("POST", "/api/plugin-connectors")](
        _ctx(body={"confirmed": True, "command": ["evil.exe"]})
    )
    assert status == 400
    assert "字段" in body["error"]
    assert service.calls == []
