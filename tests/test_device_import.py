from pathlib import Path
import time

from looklift import device_import


def test_manifest_marks_duplicate_and_filters_date(tmp_path, monkeypatch):
    source = tmp_path / "card"
    source.mkdir()
    photo = source / "sample.JPG"
    photo.write_bytes(b"photo")
    monkeypatch.setenv("LOOKLIFT_IMPORT_SOURCES", str(source))
    found = device_import.sources()
    assert found and found[0]["path"] == str(source.resolve())
    items = device_import.manifest(found[0]["id"])
    assert items[0]["name"] == "sample.JPG"
    assert items[0]["duplicate"] is False
    assert device_import.manifest(found[0]["id"], date="1900-01-01") == []


def test_import_copies_atomically(tmp_path, monkeypatch):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"raw-bytes")
    monkeypatch.setenv("LOOKLIFT_LIBRARY_DB", str(tmp_path / "library.db"))
    task_id = device_import.start([str(source)], str(tmp_path / "dest"))
    for _ in range(100):
        task = device_import.get(task_id)
        if task and task["status"] != "running":
            break
        time.sleep(0.01)
    assert task["status"] == "done"
    assert Path(task["paths"][0]).read_bytes() == b"raw-bytes"
