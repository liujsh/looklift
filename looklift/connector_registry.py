"""Connector/MCP 连接注册、授权和运行快照。"""
from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import re
from typing import Mapping

from .connector import ConnectorManifest


class ConnectorRegistryError(ValueError):
    """连接配置或生命周期操作不符合契约。"""


_CREDENTIAL_REF = re.compile(r"^(?:keyring|secret|env)://[a-z0-9][a-z0-9._/-]{0,127}$")
_WORKSPACE_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_ACCOUNT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


@dataclass(frozen=True)
class ConnectorConfig:
    """可持久化的非敏感连接配置；凭据只保留引用。"""

    manifest: ConnectorManifest
    credential_ref: str
    workspace_id: str = "default"
    account_id: str = "default"
    authorized: bool = False
    connected: bool = False

    def __post_init__(self) -> None:
        if not _CREDENTIAL_REF.fullmatch(self.credential_ref):
            raise ConnectorRegistryError("凭据引用必须是受限的 keyring/secret/env URI")
        if not _WORKSPACE_ID.fullmatch(self.workspace_id):
            raise ConnectorRegistryError("Workspace ID 不安全")
        if not _ACCOUNT_ID.fullmatch(self.account_id):
            raise ConnectorRegistryError("账号 ID 不安全")

    def public_dict(self) -> dict[str, object]:
        """返回 UI/审计可用投影，绝不暴露凭据引用。"""
        return {
            "connector_id": self.manifest.connector_id,
            "protocol": self.manifest.protocol,
            "receiver": self.manifest.receiver,
            "capabilities": tuple(sorted(self.manifest.capabilities)),
            "workspace_id": self.workspace_id,
            "account_id": self.account_id,
            "authorized": self.authorized,
            "connected": self.connected,
        }


class ConnectorRegistry:
    """进程内连接目录；运行时通过 snapshot 固定连接集合。"""

    def __init__(
        self,
        configs: Mapping[str, ConnectorConfig] | None = None,
        *,
        root: Path | None = None,
    ) -> None:
        self._configs: dict[str, ConnectorConfig] = {}
        self._root = Path(root) if root is not None else None
        self._load()
        for config in (configs or {}).values():
            self.register_config(config)

    def register(
        self,
        manifest: ConnectorManifest,
        *,
        credential_ref: str,
        workspace_id: str = "default",
        account_id: str = "default",
        authorized: bool = False,
    ) -> ConnectorConfig:
        return self.register_config(
            ConnectorConfig(
                manifest=manifest,
                credential_ref=credential_ref,
                workspace_id=workspace_id,
                account_id=account_id,
                authorized=authorized,
            )
        )

    def register_config(self, config: ConnectorConfig) -> ConnectorConfig:
        connector_id = config.manifest.connector_id
        if connector_id in self._configs:
            raise ConnectorRegistryError("Connector ID 已注册")
        self._configs[connector_id] = config
        self._persist()
        return config

    def get(self, connector_id: str) -> ConnectorConfig:
        try:
            return self._configs[connector_id]
        except KeyError as exc:
            raise ConnectorRegistryError("未知 Connector") from exc

    def list(self) -> tuple[ConnectorConfig, ...]:
        return tuple(self._configs[key] for key in sorted(self._configs))

    def authorize(self, connector_id: str) -> ConnectorConfig:
        config = self.get(connector_id)
        return self._save(replace(config, authorized=True))

    def revoke(self, connector_id: str) -> ConnectorConfig:
        config = self.get(connector_id)
        return self._save(replace(config, authorized=False, connected=False))

    def connect(self, connector_id: str) -> ConnectorConfig:
        config = self.get(connector_id)
        if not config.authorized:
            raise ConnectorRegistryError("Connector 尚未获得用户授权")
        return self._save(replace(config, connected=True))

    def disconnect(self, connector_id: str) -> ConnectorConfig:
        return self._save(replace(self.get(connector_id), connected=False))

    def snapshot(self) -> tuple[str, ...]:
        """返回按 ID 排序的已连接集合，供 Run Manifest 固定快照。"""
        return tuple(config.manifest.connector_id for config in self.list() if config.connected)

    def workspace_snapshot(self, workspace_id: str) -> tuple[str, ...]:
        if not _WORKSPACE_ID.fullmatch(workspace_id):
            raise ConnectorRegistryError("Workspace ID 不安全")
        return tuple(
            config.manifest.connector_id
            for config in self.list()
            if config.connected and config.workspace_id == workspace_id
        )

    def account_snapshot(
        self, workspace_id: str, *, receiver: str
    ) -> tuple[tuple[str, str], ...]:
        """返回当前 Workspace/接收方已连接的 `(连接, 账号)`，不含凭据。"""
        if not _WORKSPACE_ID.fullmatch(workspace_id) or not isinstance(receiver, str) or not receiver:
            raise ConnectorRegistryError("Workspace 或接收方无效")
        return tuple(
            (config.manifest.connector_id, config.account_id)
            for config in self.list()
            if config.connected
            and config.workspace_id == workspace_id
            and config.manifest.receiver == receiver
        )

    def public_list(self) -> tuple[dict[str, object], ...]:
        return tuple(config.public_dict() for config in self.list())

    def _save(self, config: ConnectorConfig) -> ConnectorConfig:
        self._configs[config.manifest.connector_id] = config
        self._persist()
        return config

    @property
    def _path(self) -> Path | None:
        return self._root / "connectors.json" if self._root is not None else None

    def _persist(self) -> None:
        path = self._path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "manifest": {
                    "connector_id": config.manifest.connector_id,
                    "protocol": config.manifest.protocol,
                    "receiver": config.manifest.receiver,
                    "capabilities": sorted(config.manifest.capabilities),
                },
                "credential_ref": config.credential_ref,
                "workspace_id": config.workspace_id,
                "account_id": config.account_id,
                "authorized": config.authorized,
                "connected": config.connected,
            }
            for config in self.list()
        ]
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        os.replace(temporary, path)

    def _load(self) -> None:
        path = self._path
        if path is None or not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(payload, list):
                raise ValueError
            for raw in payload:
                manifest = ConnectorManifest(
                    connector_id=raw["manifest"]["connector_id"],
                    protocol=raw["manifest"]["protocol"],
                    receiver=raw["manifest"]["receiver"],
                    capabilities=frozenset(raw["manifest"]["capabilities"]),
                )
                config = ConnectorConfig(
                    manifest=manifest,
                    credential_ref=raw["credential_ref"],
                    workspace_id=raw.get("workspace_id", "default"),
                    account_id=raw.get("account_id", "default"),
                    authorized=raw.get("authorized", False),
                    # 连接是进程事实；重启只恢复配置与授权，必须重新握手后才能在线。
                    connected=False,
                )
                self._configs[manifest.connector_id] = config
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ConnectorRegistryError("Connector 持久化目录损坏") from exc
