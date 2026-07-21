"""v2.3-A 本地文件夹图库的最小 SQLite 索引仓库。"""
from __future__ import annotations

import sqlite3
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image

from . import config


_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".dng", ".nef", ".cr2", ".cr3", ".arw", ".raf"}


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


@dataclass(frozen=True)
class ScanResult:
    added: int
    updated: int
    missing: int


@dataclass(frozen=True)
class ThumbnailResult:
    path: Path | None
    available: bool


class ThumbnailService:
    """只为可由 Pillow 解码的普通图片写入本地预览缓存。"""

    def __init__(self, directory: Path, max_edge: int = 512):
        self.directory = Path(directory)
        self.max_edge = max_edge

    def create(self, source: Path) -> ThumbnailResult:
        source = Path(source)
        if source.suffix.lower() not in _IMAGE_EXTENSIONS - {".dng", ".nef", ".cr2", ".cr3", ".arw", ".raf"}:
            return ThumbnailResult(None, False)
        try:
            with Image.open(source) as image:
                image = image.convert("RGB")
                image.thumbnail((self.max_edge, self.max_edge), Image.Resampling.LANCZOS)
                self.directory.mkdir(parents=True, exist_ok=True)
                target = self.directory / f"{uuid.uuid5(uuid.NAMESPACE_URL, str(source.resolve()))}.jpg"
                image.save(target, format="JPEG", quality=85, optimize=True)
        except (OSError, ValueError):
            return ThumbnailResult(None, False)
        return ThumbnailResult(target, True)


class LibraryStore:
    def __init__(self, path: Path | None = None):
        if path is None:
            path = config.library_db_path()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection, connection:
            connection.executescript("""
                CREATE TABLE IF NOT EXISTS library_roots(id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE);
                CREATE TABLE IF NOT EXISTS library_items(
                    id TEXT PRIMARY KEY, root_id TEXT NOT NULL REFERENCES library_roots(id) ON DELETE CASCADE,
                    path TEXT NOT NULL UNIQUE, display_name TEXT NOT NULL, available INTEGER NOT NULL, thumbnail_path TEXT
                );
                CREATE TABLE IF NOT EXISTS library_tags(item_id TEXT NOT NULL REFERENCES library_items(id) ON DELETE CASCADE, tag TEXT NOT NULL, PRIMARY KEY(item_id, tag));
            """)
            columns = {row[1] for row in connection.execute("PRAGMA table_info(library_items)")}
            if "thumbnail_path" not in columns:
                connection.execute("ALTER TABLE library_items ADD COLUMN thumbnail_path TEXT")

    def add_root(self, path: Path) -> LibraryRoot:
        root = str(Path(path).resolve())
        if not Path(root).is_dir():
            raise ValueError("图库根目录不存在")
        with self._connect() as connection, connection:
            row = connection.execute("SELECT id, path FROM library_roots WHERE path = ?", (root,)).fetchone()
            if row is None:
                row = {"id": uuid.uuid4().hex, "path": root}
                connection.execute("INSERT INTO library_roots(id, path) VALUES(?,?)", (row["id"], root))
        return LibraryRoot(row["id"], row["path"])

    def scan_root(self, root_id: str) -> ScanResult:
        with self._connect() as connection, connection:
            root = connection.execute("SELECT path FROM library_roots WHERE id = ?", (root_id,)).fetchone()
            if root is None:
                raise KeyError(root_id)
            discovered = {str(path.resolve()): path.name for path in Path(root["path"]).rglob("*") if path.is_file() and path.suffix.lower() in _IMAGE_EXTENSIONS}
            rows = connection.execute("SELECT id, path, available FROM library_items WHERE root_id = ?", (root_id,)).fetchall()
            existing = {row["path"]: row for row in rows}
            added = 0
            updated = 0
            thumbnails = ThumbnailService(self.path.parent / "thumbnails")
            for path, name in discovered.items():
                thumbnail = thumbnails.create(Path(path)).path
                row = existing.pop(path, None)
                if row is None:
                    connection.execute("INSERT INTO library_items(id, root_id, path, display_name, available, thumbnail_path) VALUES(?,?,?,?,1,?)", (uuid.uuid4().hex, root_id, path, name, str(thumbnail) if thumbnail else None))
                    added += 1
                elif not row["available"]:
                    connection.execute("UPDATE library_items SET available = 1, display_name = ?, thumbnail_path = ? WHERE id = ?", (name, str(thumbnail) if thumbnail else None, row["id"]))
                    updated += 1
            missing = 0
            for row in existing.values():
                if row["available"]:
                    connection.execute("UPDATE library_items SET available = 0 WHERE id = ?", (row["id"],))
                    missing += 1
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
        clauses = ["1=1"]
        values: list[str] = []
        if keyword.strip():
            clauses.append("(items.display_name LIKE ? OR items.path LIKE ?)")
            values.extend([f"%{keyword.strip()}%"] * 2)
        if tag.strip():
            clauses.append("EXISTS(SELECT 1 FROM library_tags AS tags WHERE tags.item_id = items.id AND tags.tag = ?)")
            values.append(tag.strip())
        with self._connect() as connection:
            rows = connection.execute(f"SELECT items.id, items.path, items.display_name, items.available, items.thumbnail_path FROM library_items AS items WHERE {' AND '.join(clauses)} ORDER BY items.display_name COLLATE NOCASE", values).fetchall()
        return tuple(LibraryItem(row["id"], row["path"], row["display_name"], bool(row["available"]), row["thumbnail_path"]) for row in rows)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection
