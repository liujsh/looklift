"""统一 Capability、Grant 和运行时权限交集。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import threading


class CapabilityError(PermissionError):
    pass


@dataclass(frozen=True)
class CapabilityGrant:
    subject: str
    capabilities: frozenset[str]
    project_id: str
    version_hash: str
    scope: str = "run"
    expires_at: datetime | None = None
    revoked: bool = False

    def active(self, *, now: datetime | None = None) -> bool:
        current = now or datetime.now(timezone.utc)
        return not self.revoked and (
            self.expires_at is None or current < self.expires_at
        )


def effective_capabilities(
    grant: CapabilityGrant,
    permission_profile: set[str],
    tool_contract: set[str],
) -> frozenset[str]:
    if not grant.active():
        return frozenset()
    return frozenset(grant.capabilities & permission_profile & tool_contract)


def require_capability(
    capability: str,
    *,
    grant: CapabilityGrant,
    permission_profile: set[str],
    tool_contract: set[str],
) -> None:
    if capability not in effective_capabilities(grant, permission_profile, tool_contract):
        raise CapabilityError(f"未授予能力：{capability}")


@dataclass(frozen=True)
class _ScopedToken:
    grant: CapabilityGrant
    attempt_id: str | None
    revoked: bool = False


class ScopedTokenStore:
    """进程内最小令牌权威；撤销主体后当前 Attempt 立即失效。"""

    def __init__(self) -> None:
        self._tokens: dict[str, _ScopedToken] = {}

    def issue(self, grant: CapabilityGrant, *, attempt_id: str | None = None) -> str:
        if not grant.active():
            raise CapabilityError("Grant 已过期或撤销")
        if grant.scope == "attempt" and not attempt_id:
            raise CapabilityError("Attempt Grant 必须绑定 attempt_id")
        token = secrets.token_urlsafe(32)
        self._tokens[token] = _ScopedToken(grant=grant, attempt_id=attempt_id)
        return token

    def validate(
        self,
        token: str,
        *,
        capability: str,
        project_id: str,
        attempt_id: str | None = None,
    ) -> bool:
        record = self._tokens.get(token)
        if record is None or record.revoked or not record.grant.active():
            return False
        return (
            record.grant.project_id == project_id
            and capability in record.grant.capabilities
            and (record.attempt_id is None or record.attempt_id == attempt_id)
        )

    def revoke_subject(self, subject: str, *, version_hash: str) -> None:
        for token, record in tuple(self._tokens.items()):
            if (
                record.grant.subject == subject
                and record.grant.version_hash == version_hash
            ):
                self._tokens[token] = _ScopedToken(
                    grant=record.grant,
                    attempt_id=record.attempt_id,
                    revoked=True,
                )


class CapabilityGrantStore:
    """按 Plugin + 项目保存 Grant；可选原子落盘并支持旧 dict 调用面。"""

    def __init__(self, root: Path | None = None) -> None:
        self._root = Path(root) if root is not None else None
        self._grants: dict[tuple[str, str], CapabilityGrant] = {}
        self._lock = threading.RLock()
        self._load()

    def put(self, grant: CapabilityGrant) -> CapabilityGrant:
        with self._lock:
            self._grants[(grant.subject, grant.project_id)] = grant
            self._save()
        return grant

    def active_for(self, subject: str, *, project_id: str) -> CapabilityGrant | None:
        grant = self._grants.get((subject, project_id))
        return grant if grant is not None and grant.active() else None

    def revoke(self, subject: str, *, project_id: str) -> CapabilityGrant | None:
        with self._lock:
            grant = self._grants.get((subject, project_id))
            if grant is None:
                return None
            revoked = CapabilityGrant(
                subject=grant.subject,
                capabilities=grant.capabilities,
                project_id=grant.project_id,
                version_hash=grant.version_hash,
                scope=grant.scope,
                expires_at=grant.expires_at,
                revoked=True,
            )
            self._grants[(subject, project_id)] = revoked
            self._save()
            return revoked

    def items(self):
        return tuple(self._grants.items())

    def get(self, key: tuple[str, str], default=None):
        return self._grants.get(key, default)

    def __setitem__(self, key: tuple[str, str], grant: CapabilityGrant) -> None:
        if key != (grant.subject, grant.project_id):
            raise CapabilityError("Grant 存储键与内容不一致")
        self.put(grant)

    def clear(self) -> None:
        with self._lock:
            self._grants.clear()
            self._save()

    @property
    def _path(self) -> Path | None:
        return self._root / "grants.json" if self._root is not None else None

    def _save(self) -> None:
        path = self._path
        if path is None:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "subject": grant.subject,
                "capabilities": sorted(grant.capabilities),
                "project_id": grant.project_id,
                "version_hash": grant.version_hash,
                "scope": grant.scope,
                "expires_at": grant.expires_at.isoformat() if grant.expires_at else None,
                "revoked": grant.revoked,
            }
            for _, grant in sorted(self._grants.items())
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
            for raw in payload:
                expires_at = datetime.fromisoformat(raw["expires_at"]) if raw.get("expires_at") else None
                grant = CapabilityGrant(
                    subject=raw["subject"],
                    capabilities=frozenset(raw["capabilities"]),
                    project_id=raw["project_id"],
                    version_hash=raw["version_hash"],
                    scope=raw.get("scope", "run"),
                    expires_at=expires_at,
                    revoked=raw.get("revoked", False),
                )
                self._grants[(grant.subject, grant.project_id)] = grant
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise CapabilityError("Grant 持久化目录损坏") from exc
