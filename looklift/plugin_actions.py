"""外部 Plugin 写入的持久化确认与恢复状态机。"""

from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from typing import Any, Mapping


class ActionError(ValueError):
    """Action 转移、确认或持久化不符合契约。"""


class ActionState(StrEnum):
    PENDING_CONFIRMATION = "pending_confirmation"
    CONFIRMED = "confirmed"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    UNKNOWN = "unknown"
    REJECTED = "rejected"
    CANCELLED = "cancelled"
    EXPIRED = "expired"

    @property
    def terminal(self) -> bool:
        return self in {
            self.SUCCEEDED,
            self.FAILED,
            self.UNKNOWN,
            self.REJECTED,
            self.CANCELLED,
            self.EXPIRED,
        }


@dataclass(frozen=True)
class PluginAction:
    action_id: str
    project_id: str
    plugin_identity: str
    plugin_hash: str
    schema_hash: str
    account_id: str
    arguments: Mapping[str, Any]
    asset_hashes: tuple[str, ...]
    state: ActionState
    revision: int
    confirmation_hash: str | None
    confirmation_consumed: bool
    expires_at: float | None
    result: Mapping[str, Any] | None
    created_at: str
    updated_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "arguments", dict(self.arguments))
        object.__setattr__(self, "asset_hashes", tuple(self.asset_hashes))
        if self.result is not None:
            object.__setattr__(self, "result", dict(self.result))

    @property
    def frozen_hash(self) -> str:
        payload = {
            "project_id": self.project_id,
            "plugin_identity": self.plugin_identity,
            "plugin_hash": self.plugin_hash,
            "schema_hash": self.schema_hash,
            "account_id": self.account_id,
            "arguments": self.arguments,
            "asset_hashes": self.asset_hashes,
            "revision": self.revision,
        }
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def public_dict(self) -> dict[str, Any]:
        """返回确认界面所需事实，不暴露内部摘要或确认凭证。"""
        return {
            "action_id": self.action_id,
            "project_id": self.project_id,
            "plugin_identity": self.plugin_identity,
            "account_id": self.account_id,
            "arguments": dict(self.arguments),
            "asset_hashes": list(self.asset_hashes),
            "state": self.state.value,
            "revision": self.revision,
            "expires_at": self.expires_at,
            "result": None if self.result is None else dict(self.result),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class PluginActionStore:
    """每个 Action 独立原子快照；确认只在宿主保存且仅消费一次。"""

    def __init__(
        self,
        root: Path,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._clock = clock
        self._reconcile_interrupted()

    def prepare(
        self,
        *,
        project_id: str,
        plugin_identity: str,
        plugin_hash: str,
        schema_hash: str,
        account_id: str,
        arguments: Mapping[str, Any],
        asset_hashes: tuple[str, ...],
        ttl_seconds: float = 600,
    ) -> PluginAction:
        if not all(isinstance(value, str) and value.strip() for value in (project_id, plugin_identity, account_id)):
            raise ActionError("Action 身份字段不能为空")
        if not all(_is_hash(value) for value in (plugin_hash, schema_hash, *asset_hashes)):
            raise ActionError("Action 摘要无效")
        if not isinstance(arguments, Mapping):
            raise ActionError("Action 参数必须是对象")
        if ttl_seconds <= 0:
            raise ActionError("Action 有效期必须为正数")
        now = _now()
        action = PluginAction(
            action_id=secrets.token_hex(16),
            project_id=project_id,
            plugin_identity=plugin_identity,
            plugin_hash=plugin_hash,
            schema_hash=schema_hash,
            account_id=account_id,
            arguments=dict(arguments),
            asset_hashes=asset_hashes,
            state=ActionState.PENDING_CONFIRMATION,
            revision=1,
            confirmation_hash=None,
            confirmation_consumed=False,
            expires_at=self._clock() + ttl_seconds,
            result=None,
            created_at=now,
            updated_at=now,
        )
        return self._save(action)

    def get(self, action_id: str) -> PluginAction:
        path = self._path(action_id)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["state"] = ActionState(raw["state"])
            raw["asset_hashes"] = tuple(raw["asset_hashes"])
            raw.setdefault("expires_at", None)
            return PluginAction(**raw)
        except FileNotFoundError as exc:
            raise ActionError("Action 不存在") from exc
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ActionError("Action 快照损坏") from exc

    def list(self, *, project_id: str) -> tuple[PluginAction, ...]:
        """按项目返回 Action，并在读取时收敛已过期的待确认项。"""
        if not isinstance(project_id, str) or not project_id.strip():
            raise ActionError("Action 项目不能为空")
        with self._lock:
            actions: list[PluginAction] = []
            for path in sorted(self._root.glob("*.json")):
                try:
                    action = self.get(path.stem)
                    if action.project_id != project_id:
                        continue
                    try:
                        action = self._expire(action)
                    except ActionError:
                        action = self.get(path.stem)
                    actions.append(action)
                except ActionError:
                    continue
            return tuple(actions)

    def revise(
        self,
        action_id: str,
        *,
        arguments: Mapping[str, Any],
        expected_revision: int | None = None,
    ) -> PluginAction:
        with self._lock:
            action = self.get(action_id)
            if expected_revision is not None and action.revision != expected_revision:
                raise ActionError("Action revision 已变化")
            if action.state not in {ActionState.PENDING_CONFIRMATION, ActionState.CONFIRMED}:
                raise ActionError("Action 当前状态不能修改")
            return self._save(
                replace(
                    action,
                    arguments=dict(arguments),
                    revision=action.revision + 1,
                    state=ActionState.PENDING_CONFIRMATION,
                    confirmation_hash=None,
                    confirmation_consumed=False,
                    updated_at=_now(),
                )
            )

    def confirm(self, action_id: str, *, expected_revision: int) -> PluginAction:
        with self._lock:
            action = self.get(action_id)
            action = self._expire(action)
            if action.revision != expected_revision:
                raise ActionError("Action revision 已变化，旧确认失效")
            if action.state is not ActionState.PENDING_CONFIRMATION:
                raise ActionError("Action 不在待确认状态")
            confirmed = replace(
                action,
                state=ActionState.CONFIRMED,
                confirmation_hash=action.frozen_hash,
                updated_at=_now(),
            )
            return self._save(confirmed)

    def begin_execution(self, action_id: str) -> PluginAction:
        with self._lock:
            action = self.get(action_id)
            action = self._expire(action)
            if action.state.terminal:
                raise ActionError("Action 已处于终态")
            if action.confirmation_consumed:
                raise ActionError("Action 确认已经消费")
            if action.state is not ActionState.CONFIRMED:
                raise ActionError("Action 尚未确认")
            if action.confirmation_hash != action.frozen_hash:
                raise ActionError("Action 内容变化，确认已失效")
            return self._save(
                replace(
                    action,
                    state=ActionState.EXECUTING,
                    confirmation_consumed=True,
                    updated_at=_now(),
                )
            )

    def finish(
        self,
        action_id: str,
        *,
        state: ActionState,
        result: Mapping[str, Any],
    ) -> PluginAction:
        if state not in {ActionState.SUCCEEDED, ActionState.FAILED, ActionState.UNKNOWN}:
            raise ActionError("执行结果状态无效")
        with self._lock:
            action = self.get(action_id)
            if action.state is not ActionState.EXECUTING:
                raise ActionError("只有执行中的 Action 可以完成")
            return self._save(replace(action, state=state, result=dict(result), updated_at=_now()))

    def reject(self, action_id: str) -> PluginAction:
        with self._lock:
            action = self.get(action_id)
            if action.state is not ActionState.PENDING_CONFIRMATION:
                raise ActionError("只有待确认 Action 可以拒绝")
            return self._save(replace(action, state=ActionState.REJECTED, updated_at=_now()))

    def cancel(self, action_id: str) -> PluginAction:
        with self._lock:
            action = self.get(action_id)
            if action.state.terminal:
                return action
            result = (
                {"message": "已取消本地等待；外部平台操作可能已经发生"}
                if action.state is ActionState.EXECUTING
                else {"message": "已取消"}
            )
            return self._save(
                replace(action, state=ActionState.CANCELLED, result=result, updated_at=_now())
            )

    def _expire(self, action: PluginAction) -> PluginAction:
        if (
            action.expires_at is not None
            and self._clock() >= action.expires_at
            and action.state in {ActionState.PENDING_CONFIRMATION, ActionState.CONFIRMED}
        ):
            self._save(
                replace(action, state=ActionState.EXPIRED, updated_at=_now())
            )
            raise ActionError("Action 已过期")
        return action

    def _reconcile_interrupted(self) -> None:
        for path in self._root.glob("*.json"):
            try:
                action = self.get(path.stem)
            except ActionError:
                continue
            if action.state is ActionState.EXECUTING:
                self._save(
                    replace(
                        action,
                        state=ActionState.UNKNOWN,
                        result={
                            "message": "宿主重启时外部写入仍在执行，结果未知",
                            "reason": "host_restarted",
                        },
                        updated_at=_now(),
                    )
                )

    def _path(self, action_id: str) -> Path:
        if not isinstance(action_id, str) or not action_id or not action_id.isascii() or not action_id.isalnum():
            raise ActionError("Action ID 不安全")
        return self._root / f"{action_id}.json"

    def _save(self, action: PluginAction) -> PluginAction:
        path = self._path(action.action_id)
        payload = asdict(action)
        payload["state"] = action.state.value
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        temporary.replace(path)
        return action


def _is_hash(value: str) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
