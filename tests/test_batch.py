import json
import os
from pathlib import Path

from looklift import batch


def _image(path: Path, mtime: int) -> Path:
    path.write_bytes(b"image")
    os.utime(path, (mtime, mtime))
    return path


def _groups(root: Path, count: int = 3) -> list[Path]:
    groups = []
    for index in range(count):
        group = root / f"group-{index}"
        group.mkdir()
        _image(group / "photo.jpg", 100 + index)
        groups.append(group)
    return groups


def test_scan_groups_sorts_images_by_mtime_then_name_and_limits_five(tmp_path):
    group = tmp_path / "look"
    group.mkdir()
    _image(group / "z.jpg", 1)
    _image(group / "a.png", 1)
    for index in range(5):
        _image(group / f"later-{index}.webp", 10 + index)
    (group / "notes.txt").write_text("ignore", encoding="utf-8")
    ignored = tmp_path / "no-images"
    ignored.mkdir()

    groups = batch.scan_groups(tmp_path)

    assert [item.path for item in groups] == [group]
    assert [path.name for path in groups[0].images] == [
        "a.png", "z.jpg", "later-0.webp", "later-1.webp", "later-2.webp"
    ]


def test_run_batch_writes_results_then_skips_and_force_reruns(tmp_path):
    groups = _groups(tmp_path)
    calls = []

    def analyze(images, *, style_hint, backend):
        calls.append((images, style_hint, backend))
        return {"summary": Path(images[0]).parent.name}

    first = batch.run_batch(tmp_path, analyze=analyze, style_hint="电影", backend="ollama")
    assert (first.completed, first.skipped, first.failed) == (3, 0, 0)
    assert len(calls) == 3
    for group in groups:
        result = group / batch.RESULT_NAME
        assert json.loads(result.read_text(encoding="utf-8"))["summary"] == group.name
        assert not result.with_name(result.name + ".tmp").exists()
    assert calls[0][1:] == ("电影", "ollama")

    second = batch.run_batch(tmp_path, analyze=analyze)
    assert (second.completed, second.skipped, second.failed) == (0, 3, 0)
    assert len(calls) == 3

    forced = batch.run_batch(tmp_path, analyze=analyze, force=True)
    assert (forced.completed, forced.skipped, forced.failed) == (3, 0, 0)
    assert len(calls) == 6


def test_run_batch_continues_after_group_failure_without_result(tmp_path):
    groups = _groups(tmp_path)
    visited = []

    def analyze(images, *, style_hint, backend):
        group = Path(images[0]).parent
        visited.append(group.name)
        if group.name == "group-1":
            raise RuntimeError("boom")
        return {"summary": group.name}

    result = batch.run_batch(tmp_path, analyze=analyze)

    assert visited == ["group-0", "group-1", "group-2"]
    assert (result.completed, result.skipped, result.failed) == (2, 0, 1)
    assert result.failures == {"group-1": "boom"}
    assert not (groups[1] / batch.RESULT_NAME).exists()
    assert (groups[2] / batch.RESULT_NAME).exists()


def test_force_failure_removes_stale_checkpoint(tmp_path):
    group = _groups(tmp_path, count=1)[0]
    output = group / batch.RESULT_NAME
    output.write_text('{"summary":"old"}', encoding="utf-8")

    def fail(*args, **kwargs):
        raise RuntimeError("new run failed")

    result = batch.run_batch(tmp_path, analyze=fail, force=True)
    assert result.failed == 1
    assert not output.exists()


def test_run_batch_empty_directory(tmp_path):
    result = batch.run_batch(tmp_path, analyze=lambda *args, **kwargs: {})
    assert result.total == 0
    assert (result.completed, result.skipped, result.failed) == (0, 0, 0)
