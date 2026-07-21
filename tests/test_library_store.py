from pathlib import Path

from PIL import Image

from looklift.library_store import LibraryStore, ThumbnailService


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
