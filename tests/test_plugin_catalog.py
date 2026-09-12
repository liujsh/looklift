from __future__ import annotations

import base64
import hashlib
import json

import pytest
import httpx
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from looklift.plugin_catalog import (
    PluginCatalogCache,
    PluginCatalogError,
    PluginCatalogVerifier,
    HttpxCatalogFetcher,
    download_catalog_package,
    install_catalog_plugin,
)


def _envelope(private_key, *, revision=1, expires_at=2_000.0, url="https://example.test/plugin.zip"):
    signed = {
        "schema_version": 1,
        "revision": revision,
        "issued_at": 1_000.0,
        "expires_at": expires_at,
        "plugins": [
            {
                "name": "notes",
                "version": "1.2.3",
                "url": url,
                "sha256": "a" * 64,
                "license": "MIT",
                "platforms": ["win32"],
                "capabilities": ["notes.read"],
            }
        ],
        "revoked": [],
    }
    canonical = json.dumps(signed, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return {
        "key_id": "root-2026",
        "signed": signed,
        "signature": base64.b64encode(private_key.sign(canonical)).decode(),
    }


def _verifier(private_key, *, revoked_keys=frozenset()):
    public = private_key.public_key().public_bytes_raw()
    return PluginCatalogVerifier(
        {"root-2026": public},
        revoked_key_ids=revoked_keys,
        clock=lambda: 1_500.0,
    )


def test_catalog_verifies_ed25519_signature_and_rejects_tampering():
    private = Ed25519PrivateKey.generate()
    envelope = _envelope(private)
    snapshot = _verifier(private).verify(json.dumps(envelope).encode())
    assert snapshot.revision == 1
    assert snapshot.plugins[0].name == "notes"

    envelope["signed"]["plugins"][0]["version"] = "9.9.9"
    with pytest.raises(PluginCatalogError, match="签名"):
        _verifier(private).verify(json.dumps(envelope).encode())


def test_catalog_rejects_revoked_key_and_non_https_package():
    private = Ed25519PrivateKey.generate()
    with pytest.raises(PluginCatalogError, match="撤销"):
        _verifier(private, revoked_keys=frozenset({"root-2026"})).verify(
            json.dumps(_envelope(private)).encode()
        )
    with pytest.raises(PluginCatalogError, match="HTTPS"):
        _verifier(private).verify(
            json.dumps(_envelope(private, url="http://example.test/plugin.zip")).encode()
        )


def test_catalog_cache_is_atomic_and_rejects_rollback(tmp_path):
    private = Ed25519PrivateKey.generate()
    cache = PluginCatalogCache(tmp_path, verifier=_verifier(private))
    cache.update(json.dumps(_envelope(private, revision=2)).encode())
    assert cache.load().revision == 2

    with pytest.raises(PluginCatalogError, match="回滚"):
        cache.update(json.dumps(_envelope(private, revision=1)).encode())
    assert cache.load().revision == 2


def test_catalog_refresh_uses_fixed_https_source(tmp_path):
    private = Ed25519PrivateKey.generate()
    payload = json.dumps(_envelope(private)).encode()
    seen = []
    cache = PluginCatalogCache(tmp_path, verifier=_verifier(private))

    snapshot = cache.refresh(
        "https://catalog.example.test/v1.json",
        fetch=lambda url, limit: seen.append((url, limit)) or payload,
    )

    assert snapshot.revision == 1
    assert seen == [("https://catalog.example.test/v1.json", 4 * 1024 * 1024)]


def test_catalog_cache_can_explicitly_read_stale_copy(tmp_path):
    private = Ed25519PrivateKey.generate()
    writer = PluginCatalogCache(
        tmp_path,
        verifier=PluginCatalogVerifier(
            {"root-2026": private.public_key().public_bytes_raw()},
            clock=lambda: 1_500.0,
        ),
    )
    writer.update(json.dumps(_envelope(private, expires_at=1_600.0)).encode())
    reader = PluginCatalogCache(
        tmp_path,
        verifier=PluginCatalogVerifier(
            {"root-2026": private.public_key().public_bytes_raw()},
            clock=lambda: 1_700.0,
        ),
    )
    with pytest.raises(PluginCatalogError, match="过期"):
        reader.load()
    assert reader.load(allow_expired=True).stale is True


def test_catalog_download_uses_fixed_url_digest_and_atomic_target(tmp_path):
    payload = b"verified plugin bytes"
    digest = hashlib.sha256(payload).hexdigest()
    seen = []

    target = download_catalog_package(
        "https://example.test/plugin.zip",
        expected_sha256=digest,
        destination=tmp_path / "plugin.zip",
        fetch=lambda url, limit: seen.append((url, limit)) or payload,
        max_bytes=1024,
    )
    assert target.read_bytes() == payload
    assert seen == [("https://example.test/plugin.zip", 1024)]

    with pytest.raises(PluginCatalogError, match="摘要"):
        download_catalog_package(
            "https://example.test/plugin.zip",
            expected_sha256="0" * 64,
            destination=tmp_path / "bad.zip",
            fetch=lambda _url, _limit: payload,
        )
    assert not (tmp_path / "bad.zip").exists()


def test_catalog_install_binds_signed_identity_to_package_installer(tmp_path):
    payload = b"verified plugin bytes"
    digest = hashlib.sha256(payload).hexdigest()
    private = Ed25519PrivateKey.generate()
    envelope = _envelope(private)
    envelope["signed"]["plugins"][0]["sha256"] = digest
    canonical = json.dumps(
        envelope["signed"], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    envelope["signature"] = base64.b64encode(private.sign(canonical)).decode()
    snapshot = _verifier(private).verify(json.dumps(envelope).encode())

    class FakeInstaller:
        def __init__(self):
            self.call = None

        def install(self, archive_path, **kwargs):
            self.call = (archive_path, kwargs)
            return "installed"

    installer = FakeInstaller()
    result = install_catalog_plugin(
        snapshot,
        "notes",
        "1.2.3",
        installer=installer,
        download_root=tmp_path,
        fetch=lambda _url, _limit: payload,
        confirmed=True,
        current_platform="win32",
    )

    assert result == "installed"
    assert installer.call[1]["expected_name"] == "notes"
    assert installer.call[1]["expected_license"] == "MIT"
    assert not (tmp_path / "notes-1.2.3.zip").exists()


def test_catalog_http_fetcher_streams_from_allowlisted_public_https_host():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, content=b"catalog")

    fetch = HttpxCatalogFetcher(
        allowed_hosts=frozenset({"catalog.example.test"}),
        resolver=lambda _host: ("8.8.8.8",),
        http_transport=httpx.MockTransport(handler),
    )
    assert fetch("https://catalog.example.test/v1.json", 32) == b"catalog"
    assert seen[0].headers["Accept"] == "application/json, application/octet-stream"


def test_catalog_http_fetcher_rejects_private_resolution_and_redirect():
    private = HttpxCatalogFetcher(
        allowed_hosts=frozenset({"catalog.example.test"}),
        resolver=lambda _host: ("127.0.0.1",),
        http_transport=httpx.MockTransport(lambda _request: httpx.Response(200, content=b"x")),
    )
    with pytest.raises(PluginCatalogError, match="网络范围"):
        private("https://catalog.example.test/v1.json", 32)

    redirected = HttpxCatalogFetcher(
        allowed_hosts=frozenset({"catalog.example.test"}),
        resolver=lambda _host: ("8.8.8.8",),
        http_transport=httpx.MockTransport(
            lambda _request: httpx.Response(302, headers={"Location": "https://evil.test/x"})
        ),
    )
    with pytest.raises(PluginCatalogError, match="重定向"):
        redirected("https://catalog.example.test/v1.json", 32)
