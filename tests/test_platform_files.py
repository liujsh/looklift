import pytest

from looklift import platform_files


def test_reveal_uses_argument_list_for_existing_file(tmp_path, monkeypatch):
    photo = tmp_path / "带 空格.jpg"
    photo.write_bytes(b"jpeg")
    calls = []
    monkeypatch.setattr(platform_files.sys, "platform", "win32")
    monkeypatch.setattr(platform_files.subprocess, "Popen", lambda args: calls.append(args))

    platform_files.reveal_in_explorer(photo)

    assert calls == [["explorer.exe", "/select,", str(photo.resolve())]]


def test_reveal_rejects_missing_file_before_starting_explorer(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(platform_files.subprocess, "Popen", lambda args: calls.append(args))

    with pytest.raises(FileNotFoundError):
        platform_files.reveal_in_explorer(tmp_path / "missing.jpg")

    assert calls == []
