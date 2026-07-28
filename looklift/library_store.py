"""v2.3-A 本地图库 SQLite 索引、迁移与分页查询。"""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from PIL import Image

from . import ai_proxy, config
from .library_schema import initialize_library_schema
from .library_thumbnails import ThumbnailService


_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".dng", ".nef", ".cr2", ".cr3", ".arw", ".raf"}


class ScanCancelled(RuntimeError):
    """用户取消图库扫描；已逐项提交的索引仍然保留。"""


@dataclass(frozen=True)
class LibraryRoot:
    id: str
    path: str


@dataclass(frozen=True)
class LibraryItem:
    id: str
    path: str
    display_name: str
    available: bool
    thumbnail_path: str | None
    file_size: int
    modified_ns: int
    width: int | None
    height: int | None
    file_format: str
    metadata: dict
    tags: tuple[str, ...]
    export_count: int
    last_export_at: str | None


@dataclass(frozen=True)
class ScanResult:
    added: int
    updated: int
    missing: int


@dataclass(frozen=True)
class LibraryPage:
    items: tuple[LibraryItem, ...]
    total: int
    page: int
    page_size: int


@dataclass(frozen=True)
class FolderEntry:
    name: str
    path: str
    count: int
    cover_item_id: str | None


@dataclass(frozen=True)
class FolderView:
    folders: tuple[FolderEntry, ...]
    items: tuple[LibraryItem, ...]
    total: int
    page: int
    page_size: int


class LibraryStore:
    def __init__(self, path: Path | None = None):
        if path is None:
            path = config.library_db_path()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def add_root(self, path: Path) -> LibraryRoot:
        resolved = Path(path).resolve()
        root = str(resolved)
        if not resolved.is_dir():
            raise ValueError("图库根目录不存在")
        with self._connect() as connection, connection:
            row = connection.execute("SELECT id, path FROM library_roots WHERE path = ?", (root,)).fetchone()
            if row is None:
                for existing in connection.execute("SELECT path FROM library_roots").fetchall():
                    existing_path = Path(existing["path"])
                    if resolved.is_relative_to(existing_path) or existing_path.is_relative_to(resolved):
                        raise ValueError("图库根目录不能互相包含")
                row = {"id": uuid.uuid4().hex, "path": root}
                connection.execute("INSERT INTO library_roots(id, path) VALUES(?,?)", (row["id"], root))
        return LibraryRoot(row["id"], row["path"])

    def scan_root(
        self,
        root_id: str,
        *,
        cancel_event: threading.Event | None = None,
        progress: Callable[[int, str], None] | None = None,
    ) -> ScanResult:
        with self._connect() as connection:
            root = connection.execute("SELECT path FROM library_roots WHERE id = ?", (root_id,)).fetchone()
            if root is None:
                raise KeyError(root_id)
            rows = connection.execute(
                "SELECT id, path, available, file_size, modified_ns FROM library_items WHERE root_id = ?",
                (root_id,),
            ).fetchall()
            existing = {row["path"]: row for row in rows}
            added = 0
            updated = 0
            thumbnails = ThumbnailService(self.path.parent / "thumbnails")
            scanned = 0
            for source in Path(root["path"]).rglob("*"):
                if cancel_event is not None and cancel_event.is_set():
                    raise ScanCancelled("图库扫描已取消")
                if not source.is_file() or source.suffix.lower() not in _IMAGE_EXTENSIONS:
                    continue
                resolved = str(source.resolve())
                stat = source.stat()
                row = existing.pop(resolved, None)
                changed = row is None or not row["available"] or row["file_size"] != stat.st_size or row["modified_ns"] != stat.st_mtime_ns
                details = self._inspect(source, thumbnails) if changed else None
                if row is None:
                    connection.execute(
                        """INSERT INTO library_items(
                        id, root_id, path, display_name, available, thumbnail_path, file_size,
                        modified_ns, width, height, file_format, metadata_json
                        ) VALUES(?,?,?,?,1,?,?,?,?,?,?,?)""",
                        (uuid.uuid4().hex, root_id, resolved, source.name, details[0], stat.st_size,
                         stat.st_mtime_ns, details[1], details[2], details[3], details[4]),
                    )
                    added += 1
                elif changed:
                    connection.execute(
                        """UPDATE library_items SET available=1, display_name=?, thumbnail_path=?,
                        file_size=?, modified_ns=?, width=?, height=?, file_format=?, metadata_json=? WHERE id=?""",
                        (source.name, details[0], stat.st_size, stat.st_mtime_ns, details[1],
                         details[2], details[3], details[4], row["id"]),
                    )
                    updated += 1
                connection.commit()
                scanned += 1
                if progress is not None:
                    progress(scanned, source.name)
            missing = 0
            for row in existing.values():
                if row["available"]:
                    connection.execute("UPDATE library_items SET available = 0 WHERE id = ?", (row["id"],))
                    missing += 1
            connection.commit()
        return ScanResult(added, updated, missing)

    def list_roots(self) -> tuple[LibraryRoot, ...]:
        with self._connect() as connection:
            rows = connection.execute("SELECT id, path FROM library_roots ORDER BY path COLLATE NOCASE").fetchall()
        return tuple(LibraryRoot(row["id"], row["path"]) for row in rows)

    def remove_root(self, root_id: str) -> None:
        with self._connect() as connection, connection:
            if connection.execute("DELETE FROM library_roots WHERE id = ?", (root_id,)).rowcount == 0:
                raise KeyError(root_id)

    def set_tags(self, item_id: str, tags: list[str]) -> None:
        cleaned = sorted({tag.strip() for tag in tags if tag.strip()})
        with self._connect() as connection, connection:
            if connection.execute("SELECT 1 FROM library_items WHERE id = ?", (item_id,)).fetchone() is None:
                raise KeyError(item_id)
            connection.execute("DELETE FROM library_tags WHERE item_id = ?", (item_id,))
            connection.executemany("INSERT INTO library_tags(item_id, tag) VALUES(?,?)", [(item_id, tag) for tag in cleaned])

    def list_items(self, keyword: str = "", tag: str = "") -> tuple[LibraryItem, ...]:
        return self._query_items(keyword, tag, limit=None, offset=0)

    def search_items(self, keyword: str = "", tag: str = "", *, page: int = 1, page_size: int = 48) -> LibraryPage:
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("page 必须是正整数")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 100:
            raise ValueError("page_size 必须是 1 到 100 的整数")
        clauses, values = self._filters(keyword, tag)
        with self._connect() as connection:
            total = connection.execute(
                f"SELECT COUNT(*) FROM library_items AS items WHERE {' AND '.join(clauses)}", values
            ).fetchone()[0]
        items = self._query_items(keyword, tag, limit=page_size, offset=(page - 1) * page_size)
        return LibraryPage(items, total, page, page_size)

    def get_item(self, item_id: str) -> LibraryItem:
        items = self._query_items("", "", limit=None, offset=0, item_id=item_id)
        if not items:
            raise KeyError(item_id)
        return items[0]

    def browse_folder(self, folder: str | None, *, page: int = 1, page_size: int = 48) -> FolderView:
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("page 必须是正整数")
        if isinstance(page_size, bool) or not isinstance(page_size, int) or not 1 <= page_size <= 100:
            raise ValueError("page_size 必须是 1 到 100 的整数")
        with self._connect() as connection:
            roots = connection.execute("SELECT id, path FROM library_roots ORDER BY path COLLATE NOCASE").fetchall()
            if folder is None:
                folders = tuple(self._root_folder_entry(connection, row) for row in roots)
                return FolderView(folders, (), 0, page, page_size)
            base = Path(folder)
            if not any(base == Path(r["path"]) or base.is_relative_to(Path(r["path"])) for r in roots):
                return FolderView((), (), 0, page, page_size)
            rows = connection.execute(
                "SELECT id, path, thumbnail_path FROM library_items WHERE path LIKE ? ESCAPE '\\'",
                (self._like_prefix(base),),
            ).fetchall()
        return self._folder_view_from_rows(base, rows, page, page_size)

    @staticmethod
    def _like_prefix(base: Path) -> str:
        prefix = str(base) + os.sep
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return escaped + "%"

    def _root_folder_entry(self, connection, row) -> FolderEntry:
        items = connection.execute(
            "SELECT id, thumbnail_path FROM library_items WHERE root_id = ?", (row["id"],)
        ).fetchall()
        cover = next((i["id"] for i in items if i["thumbnail_path"]), items[0]["id"] if items else None)
        return FolderEntry(Path(row["path"]).name, row["path"], len(items), cover)

    def _folder_view_from_rows(self, base: Path, rows, page: int, page_size: int) -> FolderView:
        direct_files: list[str] = []
        groups: dict[str, dict] = {}
        for row in rows:
            rel = Path(row["path"]).relative_to(base)
            if len(rel.parts) == 1:
                direct_files.append(row["id"])
                continue
            segment = rel.parts[0]
            group = groups.setdefault(segment, {"count": 0, "cover": None, "cover_has_thumb": False})
            group["count"] += 1
            if group["cover"] is None or (row["thumbnail_path"] and not group["cover_has_thumb"]):
                group["cover"] = row["id"]
                group["cover_has_thumb"] = bool(row["thumbnail_path"])
        folders = tuple(
            FolderEntry(name, str(base / name), data["count"], data["cover"])
            for name, data in sorted(groups.items(), key=lambda kv: kv[0].casefold())
        )
        total = len(direct_files)
        items = self._query_items("", "", limit=page_size, offset=(page - 1) * page_size, item_ids=direct_files)
        return FolderView(folders, items, total, page, page_size)

    def record_operation(self, item_id: str, kind: str, summary: str) -> None:
        if kind not in {"sidecar_export", "preset_export"}:
            raise ValueError("不支持的图库操作类型")
        with self._connect() as connection, connection:
            if connection.execute("SELECT 1 FROM library_items WHERE id=?", (item_id,)).fetchone() is None:
                raise KeyError(item_id)
            connection.execute(
                "INSERT INTO library_operations(id,item_id,kind,summary,created_at) VALUES(?,?,?,?,?)",
                (uuid.uuid4().hex, item_id, kind, summary, _now()),
            )

    def record_operation_for_path(self, path: Path, kind: str, summary: str) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT id FROM library_items WHERE path=?", (str(Path(path).resolve()),)).fetchone()
        if row is None:
            return False
        self.record_operation(row["id"], kind, summary)
        return True

    def _query_items(self, keyword: str, tag: str, *, limit: int | None, offset: int,
                     item_id: str | None = None, item_ids: list[str] | None = None) -> tuple[LibraryItem, ...]:
        clauses, values = self._filters(keyword, tag)
        if item_id is not None:
            clauses.append("items.id = ?")
            values.append(item_id)
        if item_ids is not None:
            if not item_ids:
                return ()
            clauses.append(f"items.id IN ({','.join('?' for _ in item_ids)})")
            values.extend(item_ids)
        sql = f"""SELECT items.*,
            (SELECT COUNT(*) FROM library_operations AS operations WHERE operations.item_id=items.id AND operations.kind LIKE '%export') AS export_count,
            (SELECT MAX(created_at) FROM library_operations AS operations WHERE operations.item_id=items.id AND operations.kind LIKE '%export') AS last_export_at
            FROM library_items AS items WHERE {' AND '.join(clauses)}
            ORDER BY items.display_name COLLATE NOCASE, items.id"""
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            values.extend([limit, offset])
        with self._connect() as connection:
            rows = connection.execute(sql, values).fetchall()
            items = []
            for row in rows:
                tags = connection.execute("SELECT tag FROM library_tags WHERE item_id=? ORDER BY tag COLLATE NOCASE", (row["id"],)).fetchall()
                items.append(LibraryItem(
                    row["id"], row["path"], row["display_name"], bool(row["available"]),
                    row["thumbnail_path"], row["file_size"], row["modified_ns"], row["width"],
                    row["height"], row["file_format"], json.loads(row["metadata_json"]),
                    tuple(tag_row["tag"] for tag_row in tags), row["export_count"], row["last_export_at"],
                ))
        return tuple(items)

    @staticmethod
    def _filters(keyword: str, tag: str) -> tuple[list[str], list[str | int]]:
        clauses = ["1=1"]
        values: list[str | int] = []
        if keyword.strip():
            clauses.append("(items.display_name LIKE ? OR items.path LIKE ?)")
            values.extend([f"%{keyword.strip()}%"] * 2)
        if tag.strip():
            clauses.append("EXISTS(SELECT 1 FROM library_tags AS tags WHERE tags.item_id = items.id AND tags.tag = ?)")
            values.append(tag.strip())
        return clauses, values

    @staticmethod
    def _inspect(source: Path, thumbnails: ThumbnailService) -> tuple[str | None, int | None, int | None, str, str]:
        thumbnail = thumbnails.create(source).path
        width = height = None
        file_format = source.suffix.lstrip(".").upper()
        metadata: dict = {}
        try:
            with Image.open(source) as image:
                width, height = image.size
                file_format = image.format or file_format
            metadata = ai_proxy.read_safe_image_info(source)
        except (OSError, ValueError):
            pass
        return str(thumbnail) if thumbnail else None, width, height, file_format, json.dumps(metadata, ensure_ascii=False, sort_keys=True)

    def _initialize(self) -> None:
        with self._connect() as connection, connection:
            initialize_library_schema(connection)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
