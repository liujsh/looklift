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


def test_library_root_scan_and_search_routes(tmp_path, monkeypatch):
    monkeypatch.setattr(api.config, "CONFIG_PATH", tmp_path / "profile" / "config.toml")
    root = tmp_path / "图库"
    root.mkdir()
    (root / "海边.jpg").write_bytes(b"jpeg")
    status, created = _call("POST", "/api/library/roots", {"path": str(root)})
    assert status == 200
    status, started = _call("POST", "/api/library/roots/<id>/scan", id=created["id"])
    assert status == 202
    while True:
        status, scanned = _call("GET", "/api/library/scans/<id>", id=started["task_id"])
        if scanned["status"] != "running":
            break
    assert scanned["status"] == "done"
    assert scanned["result"]["added"] == 1
    status, items = _call("GET", "/api/library/items", query={"keyword": "海边"})
    assert status == 200
    assert items["items"][0]["display_name"] == "海边.jpg"
    assert items["total"] == 1
    assert items["page"] == 1


def test_library_tag_route_updates_searchable_tags(tmp_path, monkeypatch):
    monkeypatch.setattr(api.config, "CONFIG_PATH", tmp_path / "profile" / "config.toml")
    root = tmp_path / "图库"
    root.mkdir()
    (root / "胶片.jpg").write_bytes(b"jpeg")
    _, created = _call("POST", "/api/library/roots", {"path": str(root)})
    from looklift.library_store import LibraryStore

    LibraryStore().scan_root(created["id"])
    _, items = _call("GET", "/api/library/items")

    status, _ = _call("PUT", "/api/library/items/<id>/tags", {"tags": ["旅行", "胶片"]}, id=items["items"][0]["id"])
    assert status == 200
    _, tagged = _call("GET", "/api/library/items", query={"tag": "胶片"})
    assert [item["display_name"] for item in tagged["items"]] == ["胶片.jpg"]
    assert tagged["items"][0]["tags"] == ["旅行", "胶片"]


def test_library_items_validate_pagination(tmp_path, monkeypatch):
    monkeypatch.setattr(api.config, "CONFIG_PATH", tmp_path / "profile" / "config.toml")

    for query in ({"page": "0"}, {"page_size": "101"}, {"page": "abc"}):
        status, body = _call("GET", "/api/library/items", query=query)

        assert status == 400
        assert "分页" in body["error"]


def test_library_scan_can_be_cancelled_and_reports_status(monkeypatch):
    calls = []

    class FakeTasks:
        @staticmethod
        def submit(root_id):
            calls.append(("submit", root_id))
            return "scan-1"

        @staticmethod
        def get(task_id):
            calls.append(("get", task_id))
            return {"status": "running", "message": "已扫描 2 个文件", "result": None, "error": None, "scanned": 2, "current": "a.jpg"}

        @staticmethod
        def cancel(task_id):
            calls.append(("cancel", task_id))
            return True

    monkeypatch.setattr(api, "library_tasks", FakeTasks)

    assert _call("POST", "/api/library/roots/<id>/scan", id="root") == (202, {"task_id": "scan-1"})
    status, task = _call("GET", "/api/library/scans/<id>", id="scan-1")
    assert status == 200 and task["scanned"] == 2
    assert _call("POST", "/api/library/scans/<id>/cancel", id="scan-1") == (200, {"ok": True})
    assert calls == [("submit", "root"), ("get", "scan-1"), ("cancel", "scan-1")]


def test_library_reveal_uses_indexed_available_path(tmp_path, monkeypatch):
    monkeypatch.setattr(api.config, "CONFIG_PATH", tmp_path / "profile" / "config.toml")
    root = tmp_path / "图库"
    root.mkdir()
    photo = root / "定位.jpg"
    photo.write_bytes(b"jpeg")
    from looklift.library_store import LibraryStore

    store = LibraryStore()
    root_record = store.add_root(root)
    store.scan_root(root_record.id)
    item = store.list_items()[0]
    revealed = []
    monkeypatch.setattr(api.platform_files, "reveal_in_explorer", lambda path: revealed.append(path))

    status, body = _call("POST", "/api/library/items/<id>/reveal", id=item.id)

    assert (status, body) == (200, {"ok": True})
    assert revealed == [photo.resolve()]


def test_library_items_include_current_formal_session_summary(
    tmp_path, monkeypatch, sample_analysis
):
    monkeypatch.setattr(api.config, "CONFIG_PATH", tmp_path / "profile" / "config.toml")
    root = tmp_path / "图库"
    root.mkdir()
    photo = root / "版本.jpg"
    photo.write_bytes(b"jpeg")
    from looklift.library_store import LibraryStore

    store = LibraryStore()
    root_record = store.add_root(root)
    store.scan_root(root_record.id)
    _, session = _call(
        "POST", "/api/sessions", {"path": str(photo), "initial_analysis": sample_analysis}
    )

    status, body = _call("GET", "/api/library/items")

    assert status == 200
    assert body["items"][0]["session_id"] == session["id"]
    assert body["items"][0]["current_version_id"] == session["current_version_id"]
