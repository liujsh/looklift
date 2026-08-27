from __future__ import annotations

import json

from looklift import config
from looklift.gui import api


def _ctx(*, entry_id: str = "preference-natural", body=None):
    return {
        "params": {"id": entry_id},
        "body": json.dumps(body, ensure_ascii=False).encode() if body is not None else None,
        "content_type": "application/json",
        "query": {},
    }


def test_context_api_crud_never_exposes_local_paths(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.toml")
    put = api.ROUTES[("PUT", "/api/memory/<id>")]
    status, entry = put(_ctx(body={"type": "preference", "content": "保持自然", "name": "自然观感"}))
    assert status == 200
    assert entry["state"] == "active"
    assert str(tmp_path) not in json.dumps(entry, ensure_ascii=False)

    status, tree = api.ROUTES[("GET", "/api/memory/tree")]({})
    assert status == 200
    assert tree["entries"][0]["id"] == "preference-natural"

    status, disabled = api.ROUTES[("DELETE", "/api/memory/<id>")](_ctx())
    assert status == 200
    assert disabled["enabled"] is False


def test_context_api_reviews_and_applies_external_proposal(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.toml")
    api.ROUTES[("PUT", "/api/memory/<id>")](_ctx(body={"type": "fact", "content": "旧事实"}))
    _, tree = api.ROUTES[("GET", "/api/memory/tree")]({})
    base_hash = tree["entries"][0]["content_hash"]

    status, proposal = api.ROUTES[("POST", "/api/proposals")](
        _ctx(body={
            "target_type": "Memory", "target_id": "preference-natural",
            "base_hash": base_hash, "patch": {"content": "新事实"},
            "source_packet_ids": ["packet-a"],
        })
    )
    assert status == 201
    proposal_id = proposal["proposal_id"]
    assert proposal["status"] == "preview"

    confirm = api.ROUTES[("POST", "/api/proposals/<id>/confirm")]
    apply = api.ROUTES[("POST", "/api/proposals/<id>/apply")]
    assert confirm(_ctx(entry_id=proposal_id))[1]["status"] == "confirmed"
    assert apply(_ctx(entry_id=proposal_id))[1]["status"] == "applied"

    _, restored = api.ROUTES[("GET", "/api/memory/tree")]({})
    assert restored["entries"][0]["content"] == "新事实"
    assert restored["entries"][0]["version"] == 2


def test_context_config_defaults_to_no_automatic_extraction(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.toml")

    status, current = api.ROUTES[("GET", "/api/memory/config")]({})
    assert status == 200
    assert current == {"enabled": True, "auto_extract": False}

    status, updated = api.ROUTES[("PATCH", "/api/memory/config")](
        _ctx(body={"auto_extract": True})
    )
    assert status == 200
    assert updated["auto_extract"] is True


def test_context_api_rejects_non_text_fields_instead_of_stringifying_them(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "config.toml")

    status, body = api.ROUTES[("PUT", "/api/memory/<id>")](
        _ctx(body={"type": "fact", "content": {"api_key": "secret"}})
    )

    assert status == 400
    assert "字符串" in body["error"]
