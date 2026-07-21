from __future__ import annotations

import json

from looklift.gui import api


def _call(method: str, pattern: str, payload=None, query=None, **params):
    body = None if payload is None else json.dumps(payload).encode()
    return api.ROUTES[(method, pattern)]({
        "params": params,
        "body": body,
        "query": query or {},
    })


def test_session_create_commit_and_failed_messages(tmp_path, sample_analysis):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"jpeg")
    status, created = _call(
        "POST", "/api/sessions", {"path": str(photo), "initial_analysis": sample_analysis}
    )
    assert status == 200
    session_id = created["id"]
    initial_version = created["current_version_id"]

    changed = json.loads(json.dumps(sample_analysis))
    changed["basic"]["exposure"] = 0.3
    exchange = [
        {"role": "user", "content": "提亮"},
        {"role": "assistant", "content": "已提亮", "provider": "mock", "status": "done"},
    ]
    status, committed = _call(
        "POST",
        "/api/sessions/<id>/commit",
        {"exchange": exchange, "analysis": changed, "source": "chat"},
        id=session_id,
    )
    assert status == 200
    assert committed["current_version_id"] != initial_version
    assert committed["current_analysis"]["basic"]["exposure"] == 0.3

    status, recorded = _call(
        "POST",
        "/api/sessions/<id>/messages",
        {"exchange": [{"role": "assistant", "content": "失败", "status": "failed"}]},
        id=session_id,
    )
    assert status == 200
    assert recorded["current_version_id"] == committed["current_version_id"]
    assert recorded["messages"][-1]["status"] == "failed"

    status, restored = _call("GET", "/api/sessions/<id>", id=session_id)
    assert status == 200
    assert restored == recorded


def test_session_routes_validate_and_return_404(tmp_path, sample_analysis):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"jpeg")
    status, body = _call("POST", "/api/sessions", {"path": str(photo), "initial_analysis": []})
    assert status == 400
    assert "initial_analysis" in body["error"]

    status, body = _call("GET", "/api/sessions/<id>", id="missing")
    assert status == 404
    assert "会话" in body["error"]


def test_creating_same_photo_resumes_session(tmp_path, sample_analysis):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"jpeg")
    payload = {"path": str(photo), "initial_analysis": sample_analysis}
    _, first = _call("POST", "/api/sessions", payload)
    _, second = _call("POST", "/api/sessions", payload)
    assert second["id"] == first["id"]


def test_recent_sessions_route_returns_bounded_summaries(tmp_path, sample_analysis):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"jpeg")
    _call("POST", "/api/sessions", {"path": str(photo), "initial_analysis": sample_analysis})

    status, body = _call("GET", "/api/sessions", query={"limit": "1"})

    assert status == 200
    assert len(body["sessions"]) == 1
    assert body["sessions"][0]["display_name"] == "photo.jpg"
    assert body["sessions"][0]["source_available"] is True
    assert "image_path" not in body["sessions"][0]


def test_recent_sessions_route_validates_limit():
    for limit in ("0", "51", "abc"):
        status, body = _call("GET", "/api/sessions", query={"limit": limit})

        assert status == 400
        assert "limit" in body["error"]


def test_session_io_error_does_not_leak_local_path(monkeypatch, tmp_path, sample_analysis):
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"jpeg")

    class BrokenStore:
        def __init__(self):
            raise OSError(r"C:\Users\someone\secret\looklift.db")

    monkeypatch.setattr(api, "SessionStore", BrokenStore)
    status, body = _call(
        "POST", "/api/sessions", {"path": str(photo), "initial_analysis": sample_analysis}
    )
    assert status == 500
    assert "secret" not in body["error"]
    assert "数据库" in body["error"]
