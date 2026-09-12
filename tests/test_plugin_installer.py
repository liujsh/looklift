from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

import pytest

from looklift.plugin_installer import PluginInstallError, PluginPackageInstaller
from looklift.plugin_registry import PluginRegistry


def _write_package(path: Path, *, extra_entries=(), license_id="Apache-2.0", platforms=("win32",)) -> str:
    runtime = b"fake-runtime"
    manifest = {
        "manifest": {
            "spec_version": 2,
            "name": "redbook",
            "version": "1.0.0",
            "kind": "connector",
            "task_kind": "social_publish",
            "mode": "sidecar",
            "inputs": ["exported_assets", "text"],
            "capabilities": ["social.publish"],
            "content_hash": "a" * 64,
            "source": "official-catalog",
            "aliases": ["小红书"],
            "description": "图文发布",
        },
        "license": {"spdx": license_id},
        "platforms": list(platforms),
        "dependencies": [
            {"name": "upstream-runtime", "version": "2.5.0", "sha256": "b" * 64}
        ],
        "files": {"runtime/fake.exe": hashlib.sha256(runtime).hexdigest()},
        "tools": [
            {
                "service": "main",
                "name": "publish_content",
                "description": "发布图文",
                "input_schema": {"type": "object"},
                "capabilities": ["social.publish"],
                "risk": "external_write",
            }
        ],
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("plugin.json", json.dumps(manifest, ensure_ascii=False))
        archive.writestr("runtime/fake.exe", runtime)
        for name, content in extra_entries:
            archive.writestr(name, content)
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_installer_verifies_and_atomically_registers_package(tmp_path: Path):
    package = tmp_path / "plugin.zip"
    digest = _write_package(package)
    registry = PluginRegistry(tmp_path / "state")
    installer = PluginPackageInstaller(tmp_path / "app-data", registry=registry)

    installed = installer.install(
        package,
        expected_sha256=digest,
        confirmed=True,
        current_platform="win32",
    )

    assert installed.path == tmp_path / "app-data" / "plugins" / "redbook" / "1.0.0"
    assert (installed.path / "runtime" / "fake.exe").read_bytes() == b"fake-runtime"
    assert registry.resolve("redbook").source == "official-catalog"
    assert registry.tools_for("redbook")[0].risk == "external_write"
    assert not any((tmp_path / "app-data" / "plugin-staging").iterdir())


def test_installer_requires_confirmation_and_exact_archive_digest(tmp_path: Path):
    package = tmp_path / "plugin.zip"
    digest = _write_package(package)
    installer = PluginPackageInstaller(tmp_path / "app-data", registry=PluginRegistry())

    with pytest.raises(PluginInstallError, match="确认"):
        installer.install(package, expected_sha256=digest, confirmed=False, current_platform="win32")
    with pytest.raises(PluginInstallError, match="摘要"):
        installer.install(package, expected_sha256="0" * 64, confirmed=True, current_platform="win32")
    with pytest.raises(PluginInstallError, match="签名目录"):
        installer.install(
            package,
            expected_sha256=digest,
            confirmed=True,
            current_platform="win32",
            expected_name="different-plugin",
        )


def test_installer_rejects_path_traversal_and_unlisted_payload(tmp_path: Path):
    package = tmp_path / "plugin.zip"
    digest = _write_package(package, extra_entries=(("../escape.txt", b"escape"),))
    installer = PluginPackageInstaller(tmp_path / "app-data", registry=PluginRegistry())

    with pytest.raises(PluginInstallError, match="路径"):
        installer.install(package, expected_sha256=digest, confirmed=True, current_platform="win32")
    assert not (tmp_path / "escape.txt").exists()

    duplicate = tmp_path / "duplicate.zip"
    duplicate_digest = _write_package(
        duplicate, extra_entries=(("RUNTIME/FAKE.EXE", b"shadow"),)
    )
    with pytest.raises(PluginInstallError, match="重复路径"):
        installer.install(
            duplicate,
            expected_sha256=duplicate_digest,
            confirmed=True,
            current_platform="win32",
        )


def test_installer_rejects_license_platform_and_unpinned_dependency(tmp_path: Path):
    package = tmp_path / "plugin.zip"
    digest = _write_package(package, license_id="GPL-3.0-only")
    installer = PluginPackageInstaller(tmp_path / "app-data", registry=PluginRegistry())
    with pytest.raises(PluginInstallError, match="许可证"):
        installer.install(package, expected_sha256=digest, confirmed=True, current_platform="win32")

    package2 = tmp_path / "plugin2.zip"
    digest2 = _write_package(package2, platforms=("linux",))
    with pytest.raises(PluginInstallError, match="平台"):
        installer.install(package2, expected_sha256=digest2, confirmed=True, current_platform="win32")
