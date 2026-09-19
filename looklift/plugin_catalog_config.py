"""应用内打包的正式 Plugin 目录信任锚配置。"""

from __future__ import annotations

import base64
import binascii
import json
import re
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Mapping
from urllib.parse import urlparse


class PluginCatalogConfigError(ValueError):
    """正式目录信任配置缺失或不满足固定信任边界。"""


@dataclass(frozen=True)
class CatalogTrust:
    catalog_url: str
    allowed_hosts: frozenset[str]
    trusted_keys: Mapping[str, bytes]
    revoked_key_ids: frozenset[str]


_HOST = re.compile(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?")
_KEY_ID = re.compile(r"[a-z0-9][a-z0-9._-]{0,63}")


def load_catalog_trust(path: Path) -> CatalogTrust:
    """读取只随应用发布的公钥轮换清单，不接受用户配置替代。"""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PluginCatalogConfigError("正式插件目录尚未配置") from exc
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise PluginCatalogConfigError("正式插件目录信任配置不可读") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "schema_version",
        "catalog_url",
        "allowed_hosts",
        "keys",
    }:
        raise PluginCatalogConfigError("目录信任配置字段无效")
    if payload["schema_version"] != 1:
        raise PluginCatalogConfigError("目录信任配置版本无效")

    hosts = payload["allowed_hosts"]
    if (
        not isinstance(hosts, list)
        or not hosts
        or len(hosts) > 32
        or any(
            not isinstance(host, str)
            or host != host.casefold()
            or not _HOST.fullmatch(host)
            for host in hosts
        )
        or len(set(hosts)) != len(hosts)
    ):
        raise PluginCatalogConfigError("目录主机白名单无效")
    allowed_hosts = frozenset(hosts)

    catalog_url = payload["catalog_url"]
    parsed = urlparse(catalog_url) if isinstance(catalog_url, str) else None
    if (
        parsed is None
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.fragment
    ):
        raise PluginCatalogConfigError("目录地址必须是无凭据 HTTPS URL")
    if parsed.hostname.casefold() not in allowed_hosts:
        raise PluginCatalogConfigError("目录地址不在主机白名单")

    raw_keys = payload["keys"]
    if not isinstance(raw_keys, list) or not raw_keys or len(raw_keys) > 16:
        raise PluginCatalogConfigError("目录公钥清单无效")
    trusted: dict[str, bytes] = {}
    revoked: set[str] = set()
    active = 0
    for raw in raw_keys:
        if not isinstance(raw, dict) or set(raw) != {"id", "public_key", "status"}:
            raise PluginCatalogConfigError("目录公钥字段无效")
        key_id = raw["id"]
        status = raw["status"]
        if (
            not isinstance(key_id, str)
            or not _KEY_ID.fullmatch(key_id)
            or key_id in trusted
            or status not in {"active", "revoked"}
        ):
            raise PluginCatalogConfigError("目录公钥身份或状态无效")
        try:
            key = base64.b64decode(raw["public_key"], validate=True)
        except (TypeError, ValueError, binascii.Error) as exc:
            raise PluginCatalogConfigError("目录公钥编码无效") from exc
        if len(key) != 32:
            raise PluginCatalogConfigError("目录公钥长度无效")
        trusted[key_id] = key
        if status == "revoked":
            revoked.add(key_id)
        else:
            active += 1
    if active == 0:
        raise PluginCatalogConfigError("目录信任配置没有有效公钥")
    return CatalogTrust(
        catalog_url=catalog_url,
        allowed_hosts=allowed_hosts,
        trusted_keys=MappingProxyType(trusted),
        revoked_key_ids=frozenset(revoked),
    )


def bundled_catalog_trust_path() -> Path:
    """返回应用打包资源固定位置；缺失时由调用方显式显示未配置。"""
    return Path(__file__).with_name("plugin_catalog_trust.json")
