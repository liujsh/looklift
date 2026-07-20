"""v2.1 最小 SQLite 会话仓库：正式消息、版本和当前指针。"""
from __future__ import annotations

import json
import shutil
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

SCHEMA_VERSION = 1


class DatabaseRecoveryRequired(RuntimeError):
    """数据库损坏或版本不可写时，要求用户从只读备份恢复。"""

    def __init__(self, database: Path, backups: tuple[Path, ...]):
        super().__init__("会话数据库无法安全打开，请使用只读备份恢复。")
        self.database = database
        self.backups = backups


class ReadOnlySessionStoreError(RuntimeError):
    pass


@dataclass(frozen=True)
class MessageRecord:
    id: str
    role: str
    content: str
    provider: str | None
    status: str
    created_at: str


@dataclass(frozen=True)
class VersionRecord:
    id: str
    parent_id: str | None
    analysis: dict
    source: str
    summary: str
    created_at: str


@dataclass(frozen=True)
class SessionSnapshot:
    id: str
    image_path: str
    created_at: str
    updated_at: str
    messages: tuple[MessageRecord, ...]
    versions: tuple[VersionRecord, ...]
    current_version_id: str
    current_analysis: dict


class SessionStore:
    """每个方法使用独立连接，适配 ThreadingHTTPServer 的多线程请求。"""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else config.session_db_path()
        self.read_only = False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @classmethod
    def open_read_only(cls, path: Path) -> "SessionStore":
        store = cls.__new__(cls)
        store.path = Path(path)
        store.read_only = True
        try:
            with store._connect() as connection:
                if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("quick_check failed")
        except sqlite3.DatabaseError:
            raise DatabaseRecoveryRequired(store.path, _existing_backups(store.path)) from None
        return store

    def create_or_resume(self, image_path: str, initial_analysis: dict) -> SessionSnapshot:
        self._require_writable()
        normalized_path = str(Path(image_path).resolve())
        now = _now()
        with self._connect() as connection, connection:
            existing = connection.execute(
                "SELECT id FROM edit_sessions WHERE image_path = ?", (normalized_path,)
            ).fetchone()
            if existing is not None:
                session_id = existing["id"]
            else:
                session_id = _id()
                version_id = _id()
                connection.execute(
                    "INSERT INTO edit_sessions(id, image_path, created_at, updated_at) VALUES(?,?,?,?)",
                    (session_id, normalized_path, now, now),
                )
                connection.execute(
                    """INSERT INTO edit_versions
                    (id, session_id, parent_id, analysis_json, source, summary, created_at)
                    VALUES(?,?,?,?,?,?,?)""",
                    (
                        version_id,
                        session_id,
                        None,
                        _json(initial_analysis),
                        "initial",
                        str(initial_analysis.get("summary", "")),
                        now,
                    ),
                )
                connection.execute(
                    "INSERT INTO session_current_versions(session_id, version_id) VALUES(?,?)",
                    (session_id, version_id),
                )
        return self.load(session_id)

    def commit_exchange(
        self,
        session_id: str,
        exchange: list[dict],
        analysis: dict,
        source: str,
    ) -> SessionSnapshot:
        self._require_writable()
        messages = _validate_exchange(exchange)
        now = _now()
        with self._connect() as connection, connection:
            current = connection.execute(
                "SELECT version_id FROM session_current_versions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            if current is None:
                raise KeyError(session_id)
            self._insert_messages(connection, session_id, messages, now)
            version_id = _id()
            connection.execute(
                """INSERT INTO edit_versions
                (id, session_id, parent_id, analysis_json, source, summary, created_at)
                VALUES(?,?,?,?,?,?,?)""",
                (
                    version_id,
                    session_id,
                    current["version_id"],
                    _json(analysis),
                    source,
                    str(analysis.get("summary", "")),
                    now,
                ),
            )
            self._advance_pointer(connection, session_id, version_id)
            connection.execute(
                "UPDATE edit_sessions SET updated_at = ? WHERE id = ?", (now, session_id)
            )
        return self.load(session_id)

    def record_failed_exchange(self, session_id: str, exchange: list[dict]) -> None:
        self._require_writable()
        messages = _validate_exchange(exchange)
        now = _now()
        with self._connect() as connection, connection:
            if connection.execute(
                "SELECT 1 FROM edit_sessions WHERE id = ?", (session_id,)
            ).fetchone() is None:
                raise KeyError(session_id)
            self._insert_messages(connection, session_id, messages, now)
            connection.execute(
                "UPDATE edit_sessions SET updated_at = ? WHERE id = ?", (now, session_id)
            )

    def load(self, session_id: str) -> SessionSnapshot:
        with self._connect() as connection:
            session = connection.execute(
                "SELECT * FROM edit_sessions WHERE id = ?", (session_id,)
            ).fetchone()
            if session is None:
                raise KeyError(session_id)
            current = connection.execute(
                "SELECT version_id FROM session_current_versions WHERE session_id = ?",
                (session_id,),
            ).fetchone()
            message_rows = connection.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY rowid", (session_id,)
            ).fetchall()
            version_rows = connection.execute(
                "SELECT * FROM edit_versions WHERE session_id = ? ORDER BY rowid", (session_id,)
            ).fetchall()

        messages = tuple(MessageRecord(
            row["id"], row["role"], row["body"], row["provider"], row["status"], row["created_at"]
        ) for row in message_rows)
        versions = tuple(VersionRecord(
            row["id"], row["parent_id"], json.loads(row["analysis_json"]),
            row["source"], row["summary"], row["created_at"]
        ) for row in version_rows)
        current_id = current["version_id"]
        current_version = next(version for version in versions if version.id == current_id)
        return SessionSnapshot(
            session["id"], session["image_path"], session["created_at"], session["updated_at"],
            messages, versions, current_id, current_version.analysis,
        )

    def _initialize(self) -> None:
        existed = self.path.exists()
        try:
            with self._connect() as connection:
                if existed and connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise sqlite3.DatabaseError("quick_check failed")
                version = _read_schema_version(connection)
        except sqlite3.DatabaseError:
            raise DatabaseRecoveryRequired(self.path, _existing_backups(self.path)) from None

        if existed and version < SCHEMA_VERSION:
            rotate_database_backups(self.path)
        if version > SCHEMA_VERSION:
            raise DatabaseRecoveryRequired(self.path, _existing_backups(self.path))
        if version < SCHEMA_VERSION:
            with self._connect() as connection, connection:
                _create_schema(connection)

    def _connect(self) -> sqlite3.Connection:
        if self.read_only:
            uri = f"file:{self.path.resolve().as_posix()}?mode=ro"
            connection = sqlite3.connect(uri, uri=True)
        else:
            connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    def _insert_messages(
        self, connection: sqlite3.Connection, session_id: str, messages: list[dict], now: str
    ) -> None:
        connection.executemany(
            """INSERT INTO messages(id, session_id, role, body, provider, status, created_at)
            VALUES(?,?,?,?,?,?,?)""",
            [(_id(), session_id, item["role"], item["content"], item["provider"], item["status"], now)
             for item in messages],
        )

    def _advance_pointer(
        self, connection: sqlite3.Connection, session_id: str, version_id: str
    ) -> None:
        connection.execute(
            "UPDATE session_current_versions SET version_id = ? WHERE session_id = ?",
            (version_id, session_id),
        )

    def _require_writable(self) -> None:
        if self.read_only:
            raise ReadOnlySessionStoreError("只读会话仓库不能写入")


def rotate_database_backups(database: Path) -> None:
    """把当前数据库复制为 bak.1，并将旧备份最多轮换到 bak.3。"""
    database = Path(database)
    for older, newer in ((2, 3), (1, 2)):
        source = Path(f"{database}.bak.{older}")
        if source.is_file():
            shutil.copy2(source, Path(f"{database}.bak.{newer}"))
    shutil.copy2(database, Path(f"{database}.bak.1"))


def _create_schema(connection: sqlite3.Connection) -> None:
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS edit_sessions(
            id TEXT PRIMARY KEY, image_path TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS messages(
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES edit_sessions(id) ON DELETE CASCADE,
            role TEXT NOT NULL, body TEXT NOT NULL, provider TEXT, status TEXT NOT NULL,
            created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS edit_versions(
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES edit_sessions(id) ON DELETE CASCADE,
            parent_id TEXT REFERENCES edit_versions(id), analysis_json TEXT NOT NULL,
            source TEXT NOT NULL, summary TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS session_current_versions(
            session_id TEXT PRIMARY KEY REFERENCES edit_sessions(id) ON DELETE CASCADE,
            version_id TEXT NOT NULL REFERENCES edit_versions(id)
        );
        DELETE FROM schema_version;
    """)
    connection.execute("INSERT INTO schema_version(version) VALUES(?)", (SCHEMA_VERSION,))


def _read_schema_version(connection: sqlite3.Connection) -> int:
    table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    if table is None:
        return 0
    row = connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
    return int(row[0]) if row is not None else 0


def _validate_exchange(exchange: list[dict]) -> list[dict]:
    if not isinstance(exchange, list):
        raise TypeError("exchange 必须是数组")
    validated: list[dict] = []
    for item in exchange:
        if not isinstance(item, dict) or item.get("role") not in {"user", "assistant"}:
            raise ValueError("消息角色无效")
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            raise ValueError("消息正文不能为空")
        provider = item.get("provider")
        if provider is not None and not isinstance(provider, str):
            raise ValueError("消息 provider 无效")
        status = item.get("status", "done")
        if status not in {"done", "failed", "cancelled"}:
            raise ValueError("消息状态无效")
        validated.append({
            "role": item["role"], "content": content, "provider": provider, "status": status,
        })
    return validated


def _existing_backups(database: Path) -> tuple[Path, ...]:
    return tuple(
        backup for index in range(1, 4)
        if (backup := Path(f"{database}.bak.{index}")).is_file()
    )


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _id() -> str:
    return uuid.uuid4().hex


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
