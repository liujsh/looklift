import sqlite3
import threading

from PIL import Image

import pytest

from looklift.library_schema import LibraryDatabaseVersionError
from looklift.library_store import LibraryStore, ScanCancelled, ThumbnailService


def test_scan_root_is_idempotent_and_marks_missing_files(tmp_path):
    root = tmp_path / "图库"
    root.mkdir()
    first = root / "第一张.jpg"
    first.write_bytes(b"jpeg")
    store = LibraryStore(tmp_path / "library.db")

    added = store.add_root(root)
    assert store.scan_root(added.id).added == 1
    assert store.scan_root(added.id).added == 0
    assert [item.display_name for item in store.list_items()] == ["第一张.jpg"]

    first.unlink()
    store.scan_root(added.id)
    assert store.list_items()[0].available is False


def test_tags_and_keyword_search_are_combined(tmp_path):
    root = tmp_path / "图库"
    root.mkdir()
    (root / "海边胶片.jpg").write_bytes(b"jpeg")
    (root / "城市夜景.jpg").write_bytes(b"jpeg")
    store = LibraryStore(tmp_path / "library.db")
    library_root = store.add_root(root)
    store.scan_root(library_root.id)
    first = store.list_items(keyword="海边")[0]
    store.set_tags(first.id, ["胶片", "旅行"])

    assert [item.display_name for item in store.list_items(keyword="海边", tag="胶片")] == ["海边胶片.jpg"]
    assert store.list_items(tag="夜景") == ()


def test_remove_root_only_removes_index_not_source_files(tmp_path):
    root = tmp_path / "图库"
    root.mkdir()
    photo = root / "保留.jpg"
    photo.write_bytes(b"jpeg")
    store = LibraryStore(tmp_path / "library.db")
    library_root = store.add_root(root)
    store.scan_root(library_root.id)

    store.remove_root(library_root.id)

    assert photo.is_file()
    assert store.list_roots() == ()
    assert store.list_items() == ()


def test_overlapping_roots_are_rejected_before_duplicate_indexing(tmp_path):
    root = tmp_path / "图库"
    nested = root / "子目录"
    nested.mkdir(parents=True)
    store = LibraryStore(tmp_path / "library.db")
    store.add_root(root)

    with pytest.raises(ValueError, match="互相包含"):
        store.add_root(nested)


def test_thumbnail_service_creates_bounded_jpeg_and_keeps_raw_as_placeholder(tmp_path):
    source = tmp_path / "source.jpg"
    Image.new("RGB", (1600, 800), "red").save(source)
    thumbnails = ThumbnailService(tmp_path / "thumbs")

    result = thumbnails.create(source)
    with Image.open(result.path) as image:
        assert image.format == "JPEG"
        assert max(image.size) == 512
    assert result.available is True
    assert thumbnails.create(tmp_path / "source.cr3").available is False


def test_legacy_database_migrates_without_losing_index(tmp_path):
    database = tmp_path / "library.db"
    with sqlite3.connect(database) as connection:
        connection.executescript("""
            CREATE TABLE library_roots(id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE);
            CREATE TABLE library_items(
                id TEXT PRIMARY KEY, root_id TEXT NOT NULL, path TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL, available INTEGER NOT NULL, thumbnail_path TEXT
            );
            CREATE TABLE library_tags(item_id TEXT NOT NULL, tag TEXT NOT NULL, PRIMARY KEY(item_id, tag));
        """)
        connection.execute("INSERT INTO library_roots VALUES('root', 'C:/图库')")
        connection.execute("INSERT INTO library_items VALUES('item', 'root', 'C:/图库/a.jpg', 'a.jpg', 0, NULL)")

    store = LibraryStore(database)

    assert store.list_items()[0].id == "item"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version FROM schema_version").fetchone()[0] >= 2
        columns = {row[1] for row in connection.execute("PRAGMA table_info(library_items)")}
    assert {"file_size", "modified_ns", "width", "height", "file_format", "metadata_json"} <= columns


def test_newer_library_database_is_not_silently_downgraded(tmp_path):
    database = tmp_path / "future.db"
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE schema_version(version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_version VALUES(99)")

    with pytest.raises(LibraryDatabaseVersionError):
        LibraryStore(database)

    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version FROM schema_version").fetchone()[0] == 99


def test_rescan_keeps_item_id_and_refreshes_file_identity_and_metadata(tmp_path):
    root = tmp_path / "图库"
    root.mkdir()
    photo = root / "有信息.jpg"
    exif = Image.Exif()
    exif[34855] = 320
    Image.new("RGB", (80, 40), "blue").save(photo, exif=exif)
    store = LibraryStore(tmp_path / "library.db")
    library_root = store.add_root(root)

    store.scan_root(library_root.id)
    first = store.list_items()[0]
    photo.write_bytes(photo.read_bytes() + b"changed")
    store.scan_root(library_root.id)
    second = store.list_items()[0]

    assert second.id == first.id
    assert second.file_size > first.file_size
    assert (second.width, second.height, second.file_format) == (80, 40, "JPEG")
    assert second.metadata["iso"] == 320


def test_paginated_search_returns_tags_and_operation_summary(tmp_path):
    root = tmp_path / "图库"
    root.mkdir()
    for name in ("01.jpg", "02.jpg", "03.jpg"):
        (root / name).write_bytes(b"jpeg")
    store = LibraryStore(tmp_path / "library.db")
    library_root = store.add_root(root)
    store.scan_root(library_root.id)
    item = store.list_items()[0]
    store.set_tags(item.id, ["旅行", "旅行", "胶片"])
    store.record_operation(item.id, "sidecar_export", "已导出 RAW sidecar")

    page = store.search_items(page=1, page_size=2)

    assert page.total == 3
    assert [entry.display_name for entry in page.items] == ["01.jpg", "02.jpg"]
    assert page.items[0].tags == ("旅行", "胶片")
    assert page.items[0].export_count == 1
    assert page.items[0].last_export_at is not None


def test_cancelled_scan_keeps_incremental_rows_and_does_not_mark_unseen_files_missing(tmp_path):
    root = tmp_path / "图库"
    root.mkdir()
    for index in range(4):
        (root / f"{index}.jpg").write_bytes(b"jpeg")
    store = LibraryStore(tmp_path / "library.db")
    library_root = store.add_root(root)
    store.scan_root(library_root.id)
    cancel = threading.Event()

    def stop_after_first(scanned: int, _current: str) -> None:
        if scanned == 1:
            cancel.set()

    with pytest.raises(ScanCancelled):
        store.scan_root(library_root.id, cancel_event=cancel, progress=stop_after_first)

    assert len(store.list_items()) == 4
    assert all(item.available for item in store.list_items())


def test_raw_uses_decodable_embedded_preview_before_placeholder(tmp_path):
    encoded = tmp_path / "encoded.jpg"
    Image.new("RGB", (640, 320), "green").save(encoded, "JPEG")
    raw = tmp_path / "photo.dng"
    raw.write_bytes(encoded.read_bytes())

    result = ThumbnailService(tmp_path / "thumbs").create(raw)

    assert result.available is True
    assert result.path is not None and result.path.is_file()
