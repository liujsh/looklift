"""图库数据库 schema 版本检查与非破坏性迁移。"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = 2


class LibraryDatabaseVersionError(RuntimeError):
    """数据库来自更新版本，当前程序不得覆盖或降级。"""


def initialize_library_schema(connection: sqlite3.Connection) -> None:
    version_table = connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='schema_version'"
    ).fetchone()
    version_row = (
        connection.execute("SELECT version FROM schema_version LIMIT 1").fetchone()
        if version_table is not None
        else None
    )
    if version_row is not None and version_row["version"] > SCHEMA_VERSION:
        raise LibraryDatabaseVersionError("图库数据库来自更新版本，请升级 LookLift")

    connection.executescript("""
        CREATE TABLE IF NOT EXISTS library_roots(id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE);
        CREATE TABLE IF NOT EXISTS library_items(
            id TEXT PRIMARY KEY, root_id TEXT NOT NULL REFERENCES library_roots(id) ON DELETE CASCADE,
            path TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL,
            available INTEGER NOT NULL, thumbnail_path TEXT
        );
        CREATE TABLE IF NOT EXISTS library_tags(
            item_id TEXT NOT NULL REFERENCES library_items(id) ON DELETE CASCADE,
            tag TEXT NOT NULL, PRIMARY KEY(item_id, tag)
        );
        CREATE TABLE IF NOT EXISTS schema_version(version INTEGER NOT NULL);
    """)
    columns = {row[1] for row in connection.execute("PRAGMA table_info(library_items)")}
    additions = {
        "thumbnail_path": "TEXT",
        "file_size": "INTEGER NOT NULL DEFAULT 0",
        "modified_ns": "INTEGER NOT NULL DEFAULT 0",
        "width": "INTEGER",
        "height": "INTEGER",
        "file_format": "TEXT NOT NULL DEFAULT ''",
        "metadata_json": "TEXT NOT NULL DEFAULT '{}'",
    }
    for name, definition in additions.items():
        if name not in columns:
            connection.execute(f"ALTER TABLE library_items ADD COLUMN {name} {definition}")
    connection.executescript("""
        CREATE TABLE IF NOT EXISTS library_operations(
            id TEXT PRIMARY KEY,
            item_id TEXT NOT NULL REFERENCES library_items(id) ON DELETE CASCADE,
            kind TEXT NOT NULL, summary TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS library_items_root_id ON library_items(root_id);
        CREATE INDEX IF NOT EXISTS library_operations_item_id ON library_operations(item_id);
    """)
    if version_row is None:
        connection.execute("INSERT INTO schema_version(version) VALUES(?)", (SCHEMA_VERSION,))
    elif version_row["version"] < SCHEMA_VERSION:
        connection.execute("UPDATE schema_version SET version=?", (SCHEMA_VERSION,))
