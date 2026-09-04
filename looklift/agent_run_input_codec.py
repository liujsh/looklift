"""受保护的 Attempt 输入快照编解码（spec 8.1）。

`AgentRunInputCodec` 把运行所需的 `run_id`、`attempt_id`、`runtime_id`、模型、
Domain Pack 指纹、代理图哈希与 Provider 配置版本写入一份受保护的 Attempt 快照。
快照**只保存凭据引用和图片哈希，不保存 API Key 或原图字节**；结构字段通过
`snapshot_hash` 做完整性保护。恢复时重新解析 Provider 凭据并校验基线哈希，
任何字段不一致或哈希不符都以 `stale_attempt` 失败，保证「启动时冻结选择快照、
不因恢复而漂移」的不变量。
"""
from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Any

_SCHEMA_VERSION = 1
_SHA256 = 64


class AttemptSnapshotError(ValueError):
    """Attempt 快照损坏、格式未知或字段不一致。"""


class StaleAttemptError(AttemptSnapshotError):
    """恢复时基线或身份与当前正式版本不一致，拒绝继续。"""


@dataclass(frozen=True)
class ProtectedAttempt:
    """一次 Attempt 的受保护运行输入（不含任何明文凭据或原图字节）。"""

    run_id: str
    attempt_id: str
    runtime_id: str
    model: str
    domain_pack_hash: str
    proxy_image_hash: str
    config_version: int
    baseline_hash: str
    session_id: str | None = None


class AgentRunInputCodec:
    """创建并校验受保护的 Attempt 输入快照。"""

    @staticmethod
    def create(
        *,
        run_id: str,
        attempt_id: str,
        runtime_id: str,
        model: str,
        domain_pack_hash: str,
        proxy_image_hash: str,
        config_version: int,
        baseline_hash: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        for label, value in (
            ("run_id", run_id),
            ("attempt_id", attempt_id),
            ("runtime_id", runtime_id),
            ("model", model),
        ):
            if not isinstance(value, str) or not value.strip():
                raise AttemptSnapshotError(f"{label} 不能为空")
        for label, value in (
            ("domain_pack_hash", domain_pack_hash),
            ("proxy_image_hash", proxy_image_hash),
            ("baseline_hash", baseline_hash),
        ):
            if not isinstance(value, str) or not _is_sha256(value):
                raise AttemptSnapshotError(f"{label} 必须是小写 SHA-256")
        if not isinstance(config_version, int) or isinstance(config_version, bool) or config_version < 1:
            raise AttemptSnapshotError("config_version 必须是正整数")

        protected = ProtectedAttempt(
            run_id=run_id,
            attempt_id=attempt_id,
            runtime_id=runtime_id,
            model=model,
            domain_pack_hash=domain_pack_hash,
            proxy_image_hash=proxy_image_hash,
            config_version=config_version,
            baseline_hash=baseline_hash,
            session_id=session_id,
        )
        snapshot = _to_dict(protected)
        snapshot["schema_version"] = _SCHEMA_VERSION
        snapshot["snapshot_hash"] = _structural_hash(snapshot)
        return snapshot

    @staticmethod
    def decode(
        value: Any,
        *,
        expected_baseline_hash: str | None = None,
        expected_run_id: str | None = None,
        expected_attempt_id: str | None = None,
    ) -> ProtectedAttempt:
        """校验快照完整性并核对基线/身份；不一致抛 `StaleAttemptError`。"""
        snapshot = _mapping(value, "Attempt 快照")
        if snapshot.get("schema_version") != _SCHEMA_VERSION:
            raise AttemptSnapshotError("不支持的 Attempt 快照格式版本")

        stored_hash = snapshot.get("snapshot_hash")
        if not isinstance(stored_hash, str) or len(stored_hash) != _SHA256:
            raise AttemptSnapshotError("Attempt 快照缺少合法 snapshot_hash")
        if not _constant_equal(stored_hash, _structural_hash(snapshot)):
            raise StaleAttemptError("Attempt 快照完整性校验失败，拒绝恢复")

        try:
            protected = _from_dict(snapshot)
        except (AttemptSnapshotError, KeyError, TypeError, ValueError) as exc:
            raise AttemptSnapshotError("Attempt 快照内容无法恢复") from exc

        if expected_baseline_hash is not None and protected.baseline_hash != expected_baseline_hash:
            raise StaleAttemptError("Attempt 基线已变化，拒绝恢复")
        if expected_run_id is not None and protected.run_id != expected_run_id:
            raise StaleAttemptError("Attempt run_id 与请求不一致")
        if expected_attempt_id is not None and protected.attempt_id != expected_attempt_id:
            raise StaleAttemptError("Attempt attempt_id 与请求不一致")
        return protected


def _to_dict(protected: ProtectedAttempt) -> dict[str, Any]:
    data = asdict(protected)
    return {key: value for key, value in data.items() if value is not None}


def _from_dict(data: Mapping[str, Any]) -> ProtectedAttempt:
    return ProtectedAttempt(
        run_id=_string(data["run_id"], "run_id"),
        attempt_id=_string(data["attempt_id"], "attempt_id"),
        runtime_id=_string(data["runtime_id"], "runtime_id"),
        model=_string(data["model"], "model"),
        domain_pack_hash=_string(data["domain_pack_hash"], "domain_pack_hash"),
        proxy_image_hash=_string(data["proxy_image_hash"], "proxy_image_hash"),
        config_version=_positive_int(data["config_version"], "config_version"),
        baseline_hash=_string(data["baseline_hash"], "baseline_hash"),
        session_id=(
            _string(data["session_id"], "session_id")
            if data.get("session_id") is not None
            else None
        ),
    )


def _structural_hash(snapshot: Mapping[str, Any]) -> str:
    payload = dict(snapshot)
    payload.pop("snapshot_hash", None)
    return _sha256(_canonical_json(payload, "Attempt 快照"))


def _canonical_json(value: Any, label: str) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise AttemptSnapshotError(f"{label} 必须是合法 JSON 数据") from exc


def _mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        raise AttemptSnapshotError(f"{label} 必须是字符串键对象")
    return dict(value)


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AttemptSnapshotError(f"{label} 必须是非空字符串")
    return value


def _positive_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise AttemptSnapshotError(f"{label} 必须是正整数")
    return value


def _is_sha256(value: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == _SHA256
        and all(character in "0123456789abcdef" for character in value)
    )


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _constant_equal(left: str, right: str) -> bool:
    return hmac.compare_digest(left, right)
