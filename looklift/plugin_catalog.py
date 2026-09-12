"""Ed25519 签名插件目录、离线缓存与固定包下载。"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import secrets
import socket
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .provider_security import ProviderSecurityError, validate_provider_url


class PluginCatalogError(ValueError):
    """目录签名、版本、缓存或下载不符合供应链策略。"""


@dataclass(frozen=True)
class CatalogPlugin:
    name: str
    version: str
    url: str
    sha256: str
    license: str
    platforms: tuple[str, ...]
    capabilities: tuple[str, ...]


@dataclass(frozen=True)
class CatalogSnapshot:
    revision: int
    issued_at: float
    expires_at: float
    key_id: str
    plugins: tuple[CatalogPlugin, ...]
    revoked: frozenset[tuple[str, str, str]]
    stale: bool = False

    def resolve(self, name: str, version: str) -> CatalogPlugin:
        matches = [item for item in self.plugins if item.name == name and item.version == version]
        if len(matches) != 1:
            raise PluginCatalogError("目录中没有唯一插件版本")
        plugin = matches[0]
        if (plugin.name, plugin.version, plugin.sha256) in self.revoked:
            raise PluginCatalogError("插件版本已被目录撤销")
        return plugin


class PluginCatalogVerifier:
    """使用应用内受信 Ed25519 公钥验证完整目录快照。"""

    def __init__(
        self,
        trusted_keys: Mapping[str, bytes],
        *,
        revoked_key_ids: frozenset[str] = frozenset(),
        clock: Callable[[], float] = time.time,
        max_catalog_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        if not trusted_keys or max_catalog_bytes <= 0:
            raise PluginCatalogError("受信目录公钥或大小上限无效")
        self._keys = dict(trusted_keys)
        self._revoked_keys = revoked_key_ids
        self._clock = clock
        self._max_catalog_bytes = max_catalog_bytes

    def verify(self, payload: bytes, *, allow_expired: bool = False) -> CatalogSnapshot:
        if not isinstance(payload, bytes) or not payload or len(payload) > self._max_catalog_bytes:
            raise PluginCatalogError("签名目录为空或超过安全上限")
        try:
            envelope = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PluginCatalogError("签名目录不是有效 JSON") from exc
        if not isinstance(envelope, Mapping):
            raise PluginCatalogError("签名目录顶层必须是对象")
        key_id = envelope.get("key_id")
        if not isinstance(key_id, str) or key_id not in self._keys:
            raise PluginCatalogError("签名目录使用未知公钥")
        if key_id in self._revoked_keys:
            raise PluginCatalogError("签名目录公钥已撤销")
        signed = envelope.get("signed")
        signature_text = envelope.get("signature")
        if not isinstance(signed, Mapping) or not isinstance(signature_text, str):
            raise PluginCatalogError("签名目录信封无效")
        canonical = _canonical_bytes(signed)
        try:
            signature = base64.b64decode(signature_text, validate=True)
            Ed25519PublicKey.from_public_bytes(self._keys[key_id]).verify(signature, canonical)
        except (ValueError, binascii.Error, InvalidSignature) as exc:
            raise PluginCatalogError("签名目录签名无效") from exc
        return self._parse_snapshot(key_id, signed, allow_expired=allow_expired)

    def _parse_snapshot(
        self, key_id: str, signed: Mapping[str, Any], *, allow_expired: bool
    ) -> CatalogSnapshot:
        if signed.get("schema_version") != 1:
            raise PluginCatalogError("签名目录 Schema 版本不受支持")
        revision = signed.get("revision")
        issued_at = signed.get("issued_at")
        expires_at = signed.get("expires_at")
        if (
            not isinstance(revision, int)
            or isinstance(revision, bool)
            or revision < 1
            or not isinstance(issued_at, (int, float))
            or isinstance(issued_at, bool)
            or not isinstance(expires_at, (int, float))
            or isinstance(expires_at, bool)
            or float(expires_at) <= float(issued_at)
        ):
            raise PluginCatalogError("签名目录版本或有效期无效")
        now = self._clock()
        if float(issued_at) > now + 300:
            raise PluginCatalogError("签名目录签发时间位于未来")
        stale = now >= float(expires_at)
        if stale and not allow_expired:
            raise PluginCatalogError("签名目录已过期")
        plugins = _parse_plugins(signed.get("plugins"))
        revoked = _parse_revocations(signed.get("revoked"))
        return CatalogSnapshot(
            revision,
            float(issued_at),
            float(expires_at),
            key_id,
            plugins,
            revoked,
            stale,
        )


class PluginCatalogCache:
    """只缓存验签后的完整信封，并拒绝目录 revision 回滚。"""

    def __init__(self, root: Path, *, verifier: PluginCatalogVerifier) -> None:
        self._root = Path(root)
        self._path = self._root / "catalog.json"
        self._verifier = verifier

    def update(self, payload: bytes) -> CatalogSnapshot:
        candidate = self._verifier.verify(payload)
        if self._path.exists():
            current = self._verifier.verify(self._path.read_bytes(), allow_expired=True)
            if candidate.revision <= current.revision:
                raise PluginCatalogError("签名目录 revision 回滚或重复")
        self._root.mkdir(parents=True, exist_ok=True)
        temporary = self._root / f"catalog-{secrets.token_hex(8)}.tmp"
        try:
            temporary.write_bytes(payload)
            os.replace(temporary, self._path)
        finally:
            if temporary.exists():
                temporary.unlink()
        return candidate

    def refresh(
        self,
        url: str,
        *,
        fetch: CatalogFetcher,
        max_bytes: int = 4 * 1024 * 1024,
    ) -> CatalogSnapshot:
        """从固定 HTTPS 地址刷新；只有验签和防回滚通过后才替换缓存。"""
        payload = _fetch_bytes(url, fetch=fetch, max_bytes=max_bytes, label="签名目录")
        return self.update(payload)

    def load(self, *, allow_expired: bool = False) -> CatalogSnapshot:
        try:
            payload = self._path.read_bytes()
        except OSError as exc:
            raise PluginCatalogError("本地没有可用签名目录") from exc
        return self._verifier.verify(payload, allow_expired=allow_expired)


CatalogFetcher = Callable[[str, int], bytes]
AddressResolver = Callable[[str], tuple[str, ...]]


def _resolve(hostname: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                item[4][0]
                for item in socket.getaddrinfo(
                    hostname, None, type=socket.SOCK_STREAM
                )
            }
        )
    )


class HttpxCatalogFetcher:
    """目录专用 HTTPS GET；不继承代理，不跟随重定向，并流式执行大小限制。"""

    def __init__(
        self,
        *,
        allowed_hosts: frozenset[str],
        resolver: AddressResolver = _resolve,
        timeout_seconds: float = 30,
        http_transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not allowed_hosts or any(not host or host != host.casefold() for host in allowed_hosts):
            raise PluginCatalogError("目录传输主机白名单无效")
        if timeout_seconds <= 0:
            raise PluginCatalogError("目录传输超时无效")
        self._allowed_hosts = allowed_hosts
        self._resolver = resolver
        self._timeout = timeout_seconds
        self._transport = http_transport

    def __call__(self, url: str, max_bytes: int) -> bytes:
        _validate_https_url(url)
        if max_bytes <= 0:
            raise PluginCatalogError("目录传输响应上限无效")
        parsed = urlparse(url)
        assert parsed.hostname is not None
        if parsed.hostname.casefold() not in self._allowed_hosts:
            raise PluginCatalogError("目录下载地址不在主机白名单")
        try:
            validate_provider_url(
                url,
                resolved_ips=self._resolver(parsed.hostname),
            )
        except (OSError, ValueError, ProviderSecurityError) as exc:
            raise PluginCatalogError(str(exc) or "目录下载地址无效") from exc
        chunks: list[bytes] = []
        size = 0
        try:
            with httpx.Client(
                transport=self._transport,
                timeout=self._timeout,
                follow_redirects=False,
                trust_env=False,
            ) as client:
                with client.stream(
                    "GET",
                    url,
                    headers={"Accept": "application/json, application/octet-stream"},
                ) as response:
                    if response.is_redirect:
                        raise PluginCatalogError("目录传输禁止重定向")
                    if response.status_code >= 400:
                        raise PluginCatalogError("目录传输返回错误状态")
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > max_bytes:
                            raise PluginCatalogError("目录传输响应超过安全上限")
                        chunks.append(chunk)
        except PluginCatalogError:
            raise
        except (httpx.HTTPError, OSError) as exc:
            raise PluginCatalogError("目录传输连接失败") from exc
        return b"".join(chunks)


class CatalogPackageInstaller(Protocol):
    def install(self, archive_path: Path, **kwargs: Any) -> Any: ...


def install_catalog_plugin(
    snapshot: CatalogSnapshot,
    name: str,
    version: str,
    *,
    installer: CatalogPackageInstaller,
    download_root: Path,
    fetch: CatalogFetcher,
    confirmed: bool,
    current_platform: str,
) -> Any:
    """把验签目录项、固定下载和本地包校验串成一个安装事务入口。"""
    if not confirmed:
        raise PluginCatalogError("目录插件安装前必须获得用户确认")
    plugin = snapshot.resolve(name, version)
    archive = download_catalog_package(
        plugin.url,
        expected_sha256=plugin.sha256,
        destination=Path(download_root) / f"{plugin.name}-{plugin.version}.zip",
        fetch=fetch,
    )
    try:
        return installer.install(
            archive,
            expected_sha256=plugin.sha256,
            confirmed=True,
            current_platform=current_platform,
            expected_name=plugin.name,
            expected_version=plugin.version,
            expected_license=plugin.license,
        )
    finally:
        try:
            archive.unlink()
        except FileNotFoundError:
            pass


def download_catalog_package(
    url: str,
    *,
    expected_sha256: str,
    destination: Path,
    fetch: CatalogFetcher,
    max_bytes: int = 512 * 1024 * 1024,
) -> Path:
    """下载目录固定 URL 指向的包；Fetcher 必须按给定上限读取。"""
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256) or max_bytes <= 0:
        raise PluginCatalogError("插件包摘要或下载上限无效")
    payload = _fetch_bytes(url, fetch=fetch, max_bytes=max_bytes, label="插件包")
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise PluginCatalogError("插件包摘要不匹配")
    target = Path(destination)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.parent / f".{target.name}.{secrets.token_hex(8)}.tmp"
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()
    return target


def _parse_plugins(value: Any) -> tuple[CatalogPlugin, ...]:
    if not isinstance(value, list) or len(value) > 10_000:
        raise PluginCatalogError("签名目录插件列表无效")
    plugins: list[CatalogPlugin] = []
    identities: set[tuple[str, str]] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise PluginCatalogError("签名目录插件条目无效")
        try:
            scalar_fields = ("name", "version", "url", "sha256", "license")
            if any(not isinstance(raw[field], str) for field in scalar_fields):
                raise PluginCatalogError("签名目录插件字段类型无效")
            plugin = CatalogPlugin(
                name=raw["name"],
                version=raw["version"],
                url=raw["url"],
                sha256=raw["sha256"],
                license=raw["license"],
                platforms=_string_tuple(raw["platforms"]),
                capabilities=_string_tuple(raw["capabilities"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PluginCatalogError("签名目录插件条目缺少字段") from exc
        if (
            not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,63}", plugin.name)
            or not re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?", plugin.version)
            or not re.fullmatch(r"[0-9a-f]{64}", plugin.sha256)
            or not plugin.license
            or not plugin.platforms
        ):
            raise PluginCatalogError("签名目录插件元数据无效")
        _validate_https_url(plugin.url)
        identity = (plugin.name, plugin.version)
        if identity in identities:
            raise PluginCatalogError("签名目录包含重复插件版本")
        identities.add(identity)
        plugins.append(plugin)
    return tuple(plugins)


def _parse_revocations(value: Any) -> frozenset[tuple[str, str, str]]:
    if not isinstance(value, list) or len(value) > 10_000:
        raise PluginCatalogError("签名目录撤销列表无效")
    revoked: set[tuple[str, str, str]] = set()
    for raw in value:
        if not isinstance(raw, Mapping):
            raise PluginCatalogError("签名目录撤销条目无效")
        item = (raw.get("name"), raw.get("version"), raw.get("sha256"))
        if (
            not all(isinstance(part, str) and part for part in item)
            or not re.fullmatch(r"[0-9a-f]{64}", item[2])
        ):
            raise PluginCatalogError("签名目录撤销条目无效")
        revoked.add(item)  # type: ignore[arg-type]
    return frozenset(revoked)


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > 256:
        raise PluginCatalogError("目录字符串列表无效")
    result = tuple(value)
    if any(not isinstance(item, str) or not item for item in result):
        raise PluginCatalogError("目录字符串列表无效")
    return result


def _validate_https_url(value: str) -> None:
    parsed = urlparse(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise PluginCatalogError("插件包 URL 必须是无凭据的 HTTPS 地址")


def _fetch_bytes(
    url: str,
    *,
    fetch: CatalogFetcher,
    max_bytes: int,
    label: str,
) -> bytes:
    _validate_https_url(url)
    if max_bytes <= 0:
        raise PluginCatalogError(f"{label}下载上限无效")
    try:
        payload = fetch(url, max_bytes)
    except Exception as exc:
        raise PluginCatalogError(f"{label}下载失败") from exc
    if not isinstance(payload, bytes) or not payload or len(payload) > max_bytes:
        raise PluginCatalogError(f"{label}为空或超过下载上限")
    return payload


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise PluginCatalogError("签名目录内容不能规范化") from exc
