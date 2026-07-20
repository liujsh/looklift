"""v2.1 最小 SQLite 会话/消息/正式版本持久化。"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from looklift import config
from looklift.session_store import (
    DatabaseRecoveryRequired,
    ReadOnlySessionStoreError,
    SessionStore,
    rotate_database_backups,
)


def _exchange(text: str = "提亮一点") -> list[dict]:
    return [
        {"role": "user", "content": text, "provider": "mock", "status": "done"},
        {"role": "assistant", "content": "已建议曝光 +0.2", "provider": "mock", "status": "done"},
    ]


def test_create_or_resume_builds_initial_version_and_reuses_photo(tmp_path, sample_analysis):
    path = tmp_path / "sessions.db"
    photo = str(tmp_path / "photo.jpg")
    store = SessionStore(path)

    created = store.create_or_resume(photo, sample_analysis)
    resumed = store.create_or_resume(photo, {**sample_analysis, "summary": "不应覆盖"})

    assert resumed.id == created.id
    assert resumed.current_version_id == created.current_version_id
    assert resumed.current_analysis == sample_analysis
    assert len(resumed.versions) == 1
    assert resumed.versions[0].parent_id is None
    assert resumed.versions[0].source == "initial"
    assert resumed.messages == ()


def test_list_recent_projects_current_formal_version_and_file_availability(
    tmp_path, sample_analysis, monkeypatch
):
    timestamps = iter([
        "2026-07-20T01:00:00+00:00",
        "2026-07-20T02:00:00+00:00",
        "2026-07-20T03:00:00+00:00",
        "2026-07-20T04:00:00+00:00",
    ])
    monkeypatch.setattr("looklift.session_store._now", lambda: next(timestamps))
    store = SessionStore(tmp_path / "sessions.db")
    first_photo = tmp_path / "第一张.jpg"
    second_photo = tmp_path / "第二张.jpg"
    first_photo.write_bytes(b"jpeg")
    second_photo.write_bytes(b"jpeg")

    first = store.create_or_resume(str(first_photo), {**sample_analysis, "summary": "初始一"})
    second = store.create_or_resume(str(second_photo), {**sample_analysis, "summary": "初始二"})
    changed = {**sample_analysis, "summary": "当前正式版本"}
    store.commit_exchange(first.id, _exchange(), changed, "chat")
    second_photo.unlink()

    recent = store.list_recent(2)

    assert [item.id for item in recent] == [first.id, second.id]
    assert recent[0].display_name == "第一张.jpg"
    assert recent[0].summary == "当前正式版本"
    assert recent[0].current_version_id != first.current_version_id
    assert recent[0].source_available is True
    assert recent[1].source_available is False
    with sqlite3.connect(store.path) as connection:
        assert connection.execute("SELECT version FROM schema_version").fetchone() == (1,)


@pytest.mark.parametrize("limit", [0, 51])
def test_list_recent_rejects_limit_outside_safe_range(tmp_path, limit):
    store = SessionStore(tmp_path / "sessions.db")

    with pytest.raises(ValueError, match="1 到 50"):
        store.list_recent(limit)


def test_commit_exchange_is_atomic_and_restart_restores_current_version(tmp_path, sample_analysis):
    path = tmp_path / "sessions.db"
    store = SessionStore(path)
    initial = store.create_or_resume(str(tmp_path / "photo.jpg"), sample_analysis)
    candidate = {**sample_analysis, "summary": "提亮版本"}
    candidate["basic"] = {**sample_analysis["basic"], "exposure": 0.55}

    committed = store.commit_exchange(initial.id, _exchange(), candidate, "chat")
    restored = SessionStore(path).load(initial.id)

    assert committed.current_analysis == candidate
    assert restored == committed
    assert len(restored.messages) == 2
    assert [message.role for message in restored.messages] == ["user", "assistant"]
    assert len(restored.versions) == 2
    assert restored.versions[-1].parent_id == initial.current_version_id
    assert restored.versions[-1].source == "chat"


def test_commit_rolls_back_messages_version_and_pointer_on_failure(
    tmp_path, sample_analysis, monkeypatch
):
    store = SessionStore(tmp_path / "sessions.db")
    initial = store.create_or_resume(str(tmp_path / "photo.jpg"), sample_analysis)

    def fail_pointer(*_args):
        raise RuntimeError("injected")

    monkeypatch.setattr(store, "_advance_pointer", fail_pointer)
    with pytest.raises(RuntimeError, match="injected"):
        store.commit_exchange(initial.id, _exchange(), sample_analysis, "chat")

    restored = SessionStore(tmp_path / "sessions.db").load(initial.id)
    assert restored.messages == ()
    assert len(restored.versions) == 1
    assert restored.current_version_id == initial.current_version_id


def test_failed_exchange_records_status_without_moving_pointer(tmp_path, sample_analysis):
    store = SessionStore(tmp_path / "sessions.db")
    initial = store.create_or_resume(str(tmp_path / "photo.jpg"), sample_analysis)
    failed = [{"role": "user", "content": "失败消息", "provider": "mock", "status": "failed"}]

    store.record_failed_exchange(initial.id, failed)
    restored = store.load(initial.id)

    assert restored.current_version_id == initial.current_version_id
    assert len(restored.versions) == 1
    assert [(message.content, message.status) for message in restored.messages] == [
        ("失败消息", "failed")
    ]


def test_default_database_path_uses_config_directory(tmp_path, monkeypatch, sample_analysis):
    monkeypatch.setattr(config, "CONFIG_PATH", tmp_path / "profile" / "config.toml")

    store = SessionStore()
    store.create_or_resume(str(tmp_path / "photo.jpg"), sample_analysis)

    assert store.path == tmp_path / "profile" / "looklift.db"
    assert store.path.is_file()


def test_backup_rotation_keeps_latest_three_copies(tmp_path):
    database = tmp_path / "looklift.db"
    for content in (b"one", b"two", b"three", b"four"):
        database.write_bytes(content)
        rotate_database_backups(database)

    assert Path(f"{database}.bak.1").read_bytes() == b"four"
    assert Path(f"{database}.bak.2").read_bytes() == b"three"
    assert Path(f"{database}.bak.3").read_bytes() == b"two"


def test_version_zero_database_is_backed_up_then_migrated(tmp_path):
    database = tmp_path / "looklift.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE schema_version(version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_version VALUES (0)")

    SessionStore(database)

    assert Path(f"{database}.bak.1").is_file()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version FROM schema_version").fetchone() == (1,)
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    assert {"edit_sessions", "messages", "edit_versions", "session_current_versions"} <= tables


def test_corrupt_database_is_not_overwritten_and_reports_backups(tmp_path):
    database = tmp_path / "looklift.db"
    original = b"not-a-sqlite-database"
    database.write_bytes(original)
    Path(f"{database}.bak.1").write_bytes(b"backup")

    with pytest.raises(DatabaseRecoveryRequired) as raised:
        SessionStore(database)

    assert database.read_bytes() == original
    assert raised.value.database == database
    assert raised.value.backups == (Path(f"{database}.bak.1"),)


def test_read_only_store_can_load_but_cannot_write(tmp_path, sample_analysis):
    database = tmp_path / "looklift.db"
    writable = SessionStore(database)
    initial = writable.create_or_resume(str(tmp_path / "photo.jpg"), sample_analysis)

    readonly = SessionStore.open_read_only(database)

    assert readonly.load(initial.id).current_analysis == sample_analysis
    with pytest.raises(ReadOnlySessionStoreError):
        readonly.commit_exchange(initial.id, _exchange(), sample_analysis, "chat")
