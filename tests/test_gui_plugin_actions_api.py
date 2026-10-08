from __future__ import annotations

import json

from looklift.gui import api


class FakeActionService:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def list(self, *, project_id):
        self.calls.append(("list", project_id))
        return ({"action_id": "action1", "state": "pending_confirmation"},)

    def revise(self, action_id, **payload):
        self.calls.append(("revise", action_id, payload))
        return {"action_id": action_id, "revision": 2}

    def confirm_and_execute(self, action_id, **payload):
        self.calls.append(("confirm", action_id, payload))
        return {"action_id": action_id, "state": "succeeded"}

    def reject(self, action_id, *, project_id):
        self.calls.append(("reject", action_id, project_id))
        return {"action_id": action_id, "state": "rejected"}

    def cancel(self, action_id, *, project_id):
        self.calls.append(("cancel", action_id, project_id))
        return {"action_id": action_id, "state": "cancelled"}


def _ctx(*, body=None, action_id="action1", project_id=None):
    return {
        "params": {"id": action_id},
        "body": json.dumps(body).encode() if body is not None else None,
        "content_type": "application/json",
        "query": {} if project_id is None else {"project_id": project_id},
    }


def test_plugin_action_routes_keep_project_and_revision_contract(monkeypatch):
    service = FakeActionService()
    monkeypatch.setattr(api, "_PLUGIN_ACTION_SERVICE", service)

    status, listed = api.ROUTES[("GET", "/api/plugin-actions")](
        _ctx(project_id="project-a")
    )
    assert status == 200
    assert listed["actions"][0]["action_id"] == "action1"
    assert api.ROUTES[("POST", "/api/plugin-actions/<id>/revise")](
        _ctx(
            body={
                "project_id": "project-a",
                "expected_revision": 1,
                "arguments": {"title": "最终稿"},
            }
        )
    )[1]["revision"] == 2
    assert api.ROUTES[("POST", "/api/plugin-actions/<id>/confirm")](
        _ctx(body={"project_id": "project-a", "expected_revision": 2})
    )[1]["state"] == "succeeded"
    assert api.ROUTES[("POST", "/api/plugin-actions/<id>/reject")](
        _ctx(body={"project_id": "project-a"})
    )[1]["state"] == "rejected"
    assert api.ROUTES[("POST", "/api/plugin-actions/<id>/cancel")](
        _ctx(body={"project_id": "project-a"})
    )[1]["state"] == "cancelled"

    assert service.calls == [
        ("list", "project-a"),
        (
            "revise",
            "action1",
            {
                "project_id": "project-a",
                "expected_revision": 1,
                "arguments": {"title": "最终稿"},
            },
        ),
        (
            "confirm",
            "action1",
            {"project_id": "project-a", "expected_revision": 2},
        ),
        ("reject", "action1", "project-a"),
        ("cancel", "action1", "project-a"),
    ]


def test_plugin_action_routes_reject_unknown_fields_before_service(monkeypatch):
    service = FakeActionService()
    monkeypatch.setattr(api, "_PLUGIN_ACTION_SERVICE", service)

    status, body = api.ROUTES[("POST", "/api/plugin-actions/<id>/confirm")](
        _ctx(
            body={
                "project_id": "project-a",
                "expected_revision": 1,
                "confirmation_hash": "model-supplied",
            }
        )
    )

    assert status == 400
    assert "字段" in body["error"]
    assert service.calls == []
