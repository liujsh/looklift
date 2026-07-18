"""Tauri Python sidecar 入口特征测试。"""
from __future__ import annotations

import sys
from types import SimpleNamespace

from looklift.gui import sidecar


def test_configure_runtime_uses_writable_local_app_data(tmp_path):
    env = {"LOCALAPPDATA": str(tmp_path)}

    cache_dir = sidecar.configure_runtime(env)

    assert cache_dir == tmp_path / "looklift" / "cache" / "numba"
    assert cache_dir.is_dir()
    assert env["NUMBA_CACHE_DIR"] == str(cache_dir)


def test_configure_runtime_respects_explicit_cache_root(tmp_path):
    root = tmp_path / "custom-cache"
    env = {"LOOKLIFT_CACHE_DIR": str(root), "LOCALAPPDATA": str(tmp_path / "ignored")}

    cache_dir = sidecar.configure_runtime(env)

    assert cache_dir == root / "numba"
    assert env["NUMBA_CACHE_DIR"] == str(cache_dir)


def test_warm_engine_calls_numba_pipeline_and_pyvips(monkeypatch):
    from looklift.render import pipeline

    calls = []
    monkeypatch.setattr(pipeline, "warmup", lambda: calls.append("numba"))

    class FakeVipsImage:
        @classmethod
        def black(cls, width, height):
            calls.append(("pyvips", width, height))
            return cls()

        def avg(self):
            return 0.0

    fake_pyvips = SimpleNamespace(
        __version__="test-pyvips",
        Image=FakeVipsImage,
        version=lambda index: (8, 18, 4)[index],
    )
    monkeypatch.setitem(sys.modules, "pyvips", fake_pyvips)

    result = sidecar.warm_engine()

    assert calls == [("pyvips", 1, 1), "numba"]
    assert result["pyvips"] == "test-pyvips"
    assert result["libvips"] == "8.18.4"
    assert result["rendered"] is True


def test_probe_protocol_is_ascii_json_for_chinese_user_path(monkeypatch, tmp_path, capsys):
    cache_root = tmp_path / "中文用户"
    monkeypatch.setenv("LOOKLIFT_CACHE_DIR", str(cache_root))
    monkeypatch.setattr(
        sidecar,
        "warm_engine",
        lambda: {"numba": "test", "pyvips": "test", "libvips": "test", "rendered": True},
    )

    assert sidecar.main(["probe"]) == 0

    output = capsys.readouterr().out.strip()
    assert output.isascii()
    assert __import__("json").loads(output)["cache_dir"] == str(cache_root / "numba")


def test_serve_token_defaults_to_parent_process_environment(monkeypatch):
    monkeypatch.setenv("LOOKLIFT_STARTUP_TOKEN", "environment-secret")

    args = sidecar._parser().parse_args(["serve"])

    assert args.token == "environment-secret"
