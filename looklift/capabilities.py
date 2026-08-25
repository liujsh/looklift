"""统一 Capability、Grant 和运行时权限交集。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


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
