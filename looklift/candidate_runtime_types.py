"""候选 Runtime 的私有绑定、权威状态与不可变 Revision 类型。"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar

from .agent_tool_contract import CandidateMetrics, ParameterChange


_T = TypeVar("_T")


@dataclass(frozen=True)
class RunBinding:
    """由 Runtime 绑定且永不进入模型工具参数的运行事实。"""

    run_id: str
    attempt_id: str
    lease: str
    base_version_id: str
    image_path: Path
    max_render_calls: int = 3

    def __post_init__(self) -> None:
        for label, value in (
            ("run_id", self.run_id),
            ("attempt_id", self.attempt_id),
            ("lease", self.lease),
            ("base_version_id", self.base_version_id),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} 不能为空")
        if self.max_render_calls < 1:
            raise ValueError("max_render_calls 必须为正整数")


class RunAuthority(Protocol):
    """检查 Attempt、Lease、正式基线和取消状态。"""

    def validate(self, binding: RunBinding) -> str | None: ...

    def commit_if_current(
        self,
        binding: RunBinding,
        commit: Callable[[], _T],
    ) -> tuple[str | None, _T | None]: ...

    def cancel(self, binding: RunBinding | None = None) -> None: ...


class InMemoryRunAuthority:
    """v2.6-B 的内存权威；持久化和重启恢复留给 v2.6-E。"""

    def __init__(self, binding: RunBinding) -> None:
        self._attempt_id = binding.attempt_id
        self._lease = binding.lease
        self._base_version_id = binding.base_version_id
        self._cancelled = False
        self._lock = threading.RLock()

    def validate(self, binding: RunBinding) -> str | None:
        with self._lock:
            return self._validate_unlocked(binding)

    def _validate_unlocked(self, binding: RunBinding) -> str | None:
        if self._cancelled:
            return "cancelled"
        if (
            binding.attempt_id != self._attempt_id
            or binding.lease != self._lease
            or binding.base_version_id != self._base_version_id
        ):
            return "stale"
        return None

    def commit_if_current(
        self,
        binding: RunBinding,
        commit: Callable[[], _T],
    ) -> tuple[str | None, _T | None]:
        with self._lock:
            error = self._validate_unlocked(binding)
            return (error, None) if error is not None else (None, commit())

    def cancel(self, binding: RunBinding | None = None) -> None:
        with self._lock:
            if binding is None or self._validate_unlocked(binding) is None:
                self._cancelled = True

    def rotate_lease(self, lease: str) -> None:
        with self._lock:
            self._lease = lease

    def replace_attempt(self, attempt_id: str, lease: str) -> None:
        with self._lock:
            self._attempt_id = attempt_id
            self._lease = lease

    def change_base_version(self, version_id: str) -> None:
        with self._lock:
            self._base_version_id = version_id


class CandidateRenderer(Protocol):
    """把完整参数渲染为无元数据 JPEG，不向模型暴露私有路径。"""

    def render(self, image_path: Path, analysis: dict) -> bytes: ...


@dataclass(frozen=True)
class CandidateRevision:
    """单线候选链中的不可变快照。"""

    candidate_id: str
    parent_candidate_id: str | None
    _analysis_json: str
    preview_jpeg: bytes
    metrics: CandidateMetrics
    _changes_json: str

    @property
    def analysis(self) -> dict:
        """每次返回独立副本，避免调用方修改历史 Revision。"""
        return json.loads(self._analysis_json)

    @property
    def changes(self) -> tuple[ParameterChange, ...]:
        """返回重新解析的差异，曲线数组也不能反向修改历史。"""
        return tuple(
            ParameterChange.model_validate(item)
            for item in json.loads(self._changes_json)
        )
