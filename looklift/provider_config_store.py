"""Provider 非敏感配置与安全凭据引用的原子快照存储。"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path
from typing import Any

from .credential_store import DpapiCredentialStore
from .provider_snapshot import ProviderProtocol, ProviderSnapshot


class ProviderConfigStore:
    def __init__(self, path: Path, *, credentials: DpapiCredentialStore) -> None:
        self._path = path
        self._credentials = credentials

    @property
    def credentials(self) -> DpapiCredentialStore:
        return self._credentials

    def save(
        self,
        *,
        provider_id: str,
        base_url: str,
        model: str,
        protocol: str,
        max_tokens: int,
        api_key: str | None = None,
    ) -> ProviderSnapshot:
        existing = self.load()
        same_provider = existing is not None and existing.provider_id == provider_id
        reference = existing.api_key_ref if same_provider else None
        config_version = existing.config_version + 1 if existing else 1
        new_reference: str | None = None
        try:
            snapshot = ProviderSnapshot(
                provider_id=provider_id,
                base_url=base_url,
                model=model,
                api_key_ref="credential://pending" if api_key else reference,
                protocol=ProviderProtocol(protocol),
                max_tokens=max_tokens,
                config_version=config_version,
            )
            if api_key:
                new_reference = self._credentials.put(
                    f"{provider_id}-{config_version}", api_key
                )
                snapshot = replace(snapshot, api_key_ref=new_reference)
            self._write(snapshot)
        except Exception:
            if new_reference is not None:
                self._credentials.delete(new_reference)
            raise
        if (
            existing is not None
            and existing.api_key_ref is not None
            and existing.api_key_ref != snapshot.api_key_ref
        ):
            self._credentials.delete(existing.api_key_ref)
        return snapshot

    def load(self) -> ProviderSnapshot | None:
        if not self._path.is_file():
            return None
        value = json.loads(self._path.read_text(encoding="utf-8"))
        return ProviderSnapshot(**value)

    def query(self) -> dict[str, Any]:
        snapshot = self.load()
        if snapshot is None:
            return {"contract_version": 1, "configured": False, "has_key": False}
        return {
            "contract_version": 1,
            "configured": True,
            "provider_id": snapshot.provider_id,
            "base_url": snapshot.base_url,
            "model": snapshot.model,
            "protocol": snapshot.protocol.value,
            "max_tokens": snapshot.max_tokens,
            "config_version": snapshot.config_version,
            "has_key": snapshot.api_key_ref is not None,
        }

    def delete(self) -> None:
        snapshot = self.load()
        if snapshot is not None and snapshot.api_key_ref is not None:
            self._credentials.delete(snapshot.api_key_ref)
        if self._path.exists():
            self._path.unlink()

    def _write(self, snapshot: ProviderSnapshot) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(
                {
                    "provider_id": snapshot.provider_id,
                    "base_url": snapshot.base_url,
                    "model": snapshot.model,
                    "api_key_ref": snapshot.api_key_ref,
                    "protocol": snapshot.protocol.value,
                    "max_tokens": snapshot.max_tokens,
                    "config_version": snapshot.config_version,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        temporary.replace(self._path)
