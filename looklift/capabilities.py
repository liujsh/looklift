"""统一 Capability、Grant 和运行时权限交集。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import secrets


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
