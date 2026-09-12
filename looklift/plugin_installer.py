"""经过确认的本地 Plugin ZIP 校验与原子安装。"""

from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from .plugin_registry import (
    PluginManifest,
    PluginManifestError,
    PluginRegistry,
    PluginService,
)
from .plugin_tools import PluginTool, PluginToolError


class PluginInstallError(ValueError):
    """插件包来源、结构、许可或完整性不符合安装策略。"""


@dataclass(frozen=True)
class InstalledPlugin:
    manifest: PluginManifest
    path: Path
    archive_sha256: str


class PluginPackageInstaller:
    """只安装已下载的固定 ZIP；不执行脚本、不解析 latest、不访问网络。"""

    def __init__(
        self,
        root: Path,
        *,
        registry: PluginRegistry,
        allowed_licenses: frozenset[str] = frozenset(
            {"Apache-2.0", "MIT", "BSD-2-Clause", "BSD-3-Clause", "ISC"}
        ),
        max_files: int = 2_000,
        max_uncompressed_bytes: int = 512 * 1024 * 1024,
        max_compression_ratio: int = 200,
    ) -> None:
        self._root = Path(root).resolve()
        self._plugins = self._root / "plugins"
        self._staging = self._root / "plugin-staging"
        self._registry = registry
        self._allowed_licenses = allowed_licenses
        self._max_files = max_files
        self._max_uncompressed_bytes = max_uncompressed_bytes
        self._max_compression_ratio = max_compression_ratio
        self._plugins.mkdir(parents=True, exist_ok=True)
        self._staging.mkdir(parents=True, exist_ok=True)

    def install(
        self,
        archive_path: Path,
        *,
        expected_sha256: str,
        confirmed: bool,
        current_platform: str | None = None,
        expected_name: str | None = None,
        expected_version: str | None = None,
        expected_license: str | None = None,
    ) -> InstalledPlugin:
        if not confirmed:
            raise PluginInstallError("安装前必须获得用户确认")
        archive = Path(archive_path)
        try:
            archive_digest = hashlib.sha256(archive.read_bytes()).hexdigest()
        except OSError as exc:
            raise PluginInstallError("插件安装包不可读") from exc
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256) or archive_digest != expected_sha256:
            raise PluginInstallError("插件安装包摘要不匹配")

        operation = (self._staging / secrets.token_hex(16)).resolve()
        if operation.parent != self._staging:
            raise PluginInstallError("插件暂存路径无效")
        operation.mkdir()
        extracted = operation / "package"
        extracted.mkdir()
        try:
            with zipfile.ZipFile(archive) as package:
                files = self._validate_archive(package)
                raw_manifest = self._read_manifest(package)
                manifest, tools, license_id = self._parse_manifest(
                    raw_manifest,
                    current_platform=current_platform or sys.platform,
                )
                if (
                    (expected_name is not None and manifest.name != expected_name)
                    or (expected_version is not None and manifest.version != expected_version)
                    or (expected_license is not None and license_id != expected_license)
                ):
                    raise PluginInstallError("插件包身份与签名目录不匹配")
                self._validate_file_inventory(package, raw_manifest, files)
                package.extractall(extracted)
            target = (self._plugins / manifest.name / manifest.version).resolve()
            expected_parent = (self._plugins / manifest.name).resolve()
            if target.parent != expected_parent or expected_parent.parent != self._plugins:
                raise PluginInstallError("插件安装目标路径无效")
            if target.exists() or any(
                item["name"] == manifest.name and item["version"] == manifest.version
                for item in self._registry.list(include_disabled=True)
            ):
                raise PluginInstallError("Plugin 版本已安装")
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(extracted, target)
            try:
                self._registry.install(manifest, tools=tools)
            except Exception:
                shutil.rmtree(target, ignore_errors=True)
                raise
            return InstalledPlugin(manifest, target, archive_digest)
        except (zipfile.BadZipFile, OSError, KeyError, TypeError, ValueError, PluginManifestError, PluginToolError) as exc:
            if isinstance(exc, PluginInstallError):
                raise
            raise PluginInstallError(str(exc) or "插件安装包无效") from exc
        finally:
            if operation.exists():
                shutil.rmtree(operation)

    def _validate_archive(self, package: zipfile.ZipFile) -> tuple[zipfile.ZipInfo, ...]:
        entries = tuple(package.infolist())
        files = tuple(item for item in entries if not item.is_dir())
        if not files or len(files) > self._max_files:
            raise PluginInstallError("插件包文件数量超过安全上限")
        normalized_names = [item.filename.casefold() for item in entries]
        if len(set(normalized_names)) != len(normalized_names):
            raise PluginInstallError("插件包包含重复路径")
        total = 0
        for item in entries:
            _safe_archive_name(item.filename)
            mode = item.external_attr >> 16
            if stat.S_IFMT(mode) == stat.S_IFLNK:
                raise PluginInstallError("插件包不允许符号链接")
            total += item.file_size
            if item.file_size and item.compress_size == 0:
                raise PluginInstallError("插件包压缩比异常")
            if item.compress_size and item.file_size / item.compress_size > self._max_compression_ratio:
                raise PluginInstallError("插件包疑似压缩炸弹")
        if total > self._max_uncompressed_bytes:
            raise PluginInstallError("插件包解压大小超过安全上限")
        return files

    def _read_manifest(self, package: zipfile.ZipFile) -> Mapping[str, Any]:
        try:
            info = package.getinfo("plugin.json")
        except KeyError as exc:
            raise PluginInstallError("插件包缺少 plugin.json") from exc
        if info.file_size > 1024 * 1024:
            raise PluginInstallError("plugin.json 超过安全上限")
        try:
            value = json.loads(package.read(info))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PluginInstallError("plugin.json 不是有效 JSON") from exc
        if not isinstance(value, Mapping):
            raise PluginInstallError("plugin.json 顶层必须是对象")
        return value

    def _parse_manifest(
        self,
        value: Mapping[str, Any],
        *,
        current_platform: str,
    ) -> tuple[PluginManifest, tuple[PluginTool, ...], str]:
        raw = value.get("manifest")
        if not isinstance(raw, Mapping):
            raise PluginInstallError("插件 Manifest 无效")
        license_info = value.get("license")
        license_id = license_info.get("spdx") if isinstance(license_info, Mapping) else None
        if license_id not in self._allowed_licenses:
            raise PluginInstallError("插件许可证不在允许清单")
        platforms = value.get("platforms")
        if not isinstance(platforms, list) or current_platform not in platforms:
            raise PluginInstallError("插件不兼容当前平台")
        self._validate_dependencies(value.get("dependencies", []))
        manifest = PluginManifest(
            spec_version=raw["spec_version"],
            name=raw["name"],
            version=raw["version"],
            kind=raw["kind"],
            task_kind=raw["task_kind"],
            mode=raw["mode"],
            inputs=tuple(raw["inputs"]),
            capabilities=frozenset(raw["capabilities"]),
            content_hash=raw["content_hash"],
            source=raw.get("source", "local"),
            aliases=tuple(raw.get("aliases", ())),
            description=raw.get("description", ""),
            services=self._parse_services(
                value.get("services", []), value.get("files")
            ),
        )
        raw_tools = value.get("tools", [])
        if not isinstance(raw_tools, list):
            raise PluginInstallError("插件工具目录无效")
        tools = tuple(
            PluginTool(
                plugin_name=manifest.name,
                plugin_version=manifest.version,
                plugin_hash=manifest.content_hash,
                service=item["service"],
                name=item["name"],
                description=item.get("description", ""),
                input_schema=item["input_schema"],
                capabilities=frozenset(item["capabilities"]),
                risk=item["risk"],
                aliases=tuple(item.get("aliases", ())),
                task_tags=tuple(item.get("task_tags", ())),
                requires_account=bool(item.get("requires_account", False)),
            )
            for item in raw_tools
        )
        return manifest, tools, license_id

    def _parse_services(
        self, value: Any, files: Any
    ) -> tuple[PluginService, ...]:
        if not isinstance(value, list) or not isinstance(files, Mapping):
            raise PluginInstallError("插件 Service 或文件清单无效")
        services: list[PluginService] = []
        for raw in value:
            if not isinstance(raw, Mapping):
                raise PluginInstallError("插件 Service 声明无效")
            try:
                entrypoint = raw["entrypoint"]
                entrypoint_sha256 = raw["entrypoint_sha256"]
                if files.get(entrypoint) != entrypoint_sha256:
                    raise PluginInstallError("插件 Service 入口未绑定文件清单摘要")
                services.append(
                    PluginService(
                        name=raw["name"],
                        transport=raw["transport"],
                        entrypoint=entrypoint,
                        entrypoint_sha256=entrypoint_sha256,
                        arguments=tuple(raw.get("arguments", ())),
                        credential_env=raw.get("credential_env"),
                    )
                )
            except (KeyError, TypeError) as exc:
                raise PluginInstallError("插件 Service 声明缺少字段") from exc
        return tuple(services)

    def _validate_dependencies(self, dependencies: Any) -> None:
        if not isinstance(dependencies, list):
            raise PluginInstallError("插件依赖清单无效")
        for item in dependencies:
            if not isinstance(item, Mapping):
                raise PluginInstallError("插件依赖必须固定版本和摘要")
            if (
                not isinstance(item.get("name"), str)
                or not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", str(item.get("version", "")))
                or not re.fullmatch(r"[0-9a-f]{64}", str(item.get("sha256", "")))
            ):
                raise PluginInstallError("插件依赖必须固定版本和摘要")

    def _validate_file_inventory(
        self,
        package: zipfile.ZipFile,
        manifest: Mapping[str, Any],
        files: tuple[zipfile.ZipInfo, ...],
    ) -> None:
        declared = manifest.get("files")
        if not isinstance(declared, Mapping):
            raise PluginInstallError("插件文件清单无效")
        actual = {item.filename for item in files if item.filename != "plugin.json"}
        if actual != set(declared):
            raise PluginInstallError("插件包含未列入清单的文件")
        for name, expected in declared.items():
            if not re.fullmatch(r"[0-9a-f]{64}", str(expected)):
                raise PluginInstallError("插件文件摘要无效")
            if hashlib.sha256(package.read(name)).hexdigest() != expected:
                raise PluginInstallError("插件文件摘要不匹配")


def _safe_archive_name(value: str) -> PurePosixPath:
    if (
        "\\" in value
        or re.search(r"[<>:\"|?*\x00-\x1f]", value)
        or value.startswith(("/", "\\"))
    ):
        raise PluginInstallError("插件包包含不安全路径")
    path = PurePosixPath(value)
    if not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise PluginInstallError("插件包包含不安全路径")
    reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
    if any(part.rstrip(". ").split(".", 1)[0].casefold() in reserved for part in path.parts):
        raise PluginInstallError("插件包包含 Windows 保留路径")
    return path
