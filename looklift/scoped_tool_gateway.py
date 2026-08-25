"""绑定 CandidateRuntime 的一次性最小工具权限网关。"""

from __future__ import annotations

import secrets
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .agent_tool_contract import FinishCandidateInput, RenderCandidateInput
from .candidate_runtime import CandidateRuntime


_ALLOWED_TOOLS = frozenset({"render_candidate", "finish_candidate"})


def agent_tool_definitions() -> tuple[dict[str, Any], ...]:
    """从 Pydantic 单一真相源投影传输无关的 Tool Schema。"""
    return (
        {
            "name": "render_candidate",
            "description": "渲染白盒参数候选并返回真实预览反馈。",
            "inputSchema": RenderCandidateInput.model_json_schema(),
        },
        {
            "name": "finish_candidate",
            "description": "记录模型终态，不提交正式版本。",
            "inputSchema": FinishCandidateInput.model_json_schema(),
        },
    )


@dataclass(frozen=True)
class ScopedToolGrant:
    """只把不含身份信息的随机 Token 交给传输层。"""

    token: str
    expires_at: float


@dataclass(frozen=True)
class GatewayToolResult:
    """统一 Tool 结果；预览字节由具体 Harness 转成图片或隔离文件。"""

    payload: Mapping[str, Any]
    preview_jpeg: bytes | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", dict(self.payload))


@dataclass
class _GrantState:
    runtime: CandidateRuntime
    expires_at: float
    revoked: bool = False


class ScopedToolGateway:
    """只授予两个候选工具，不接受模型提供 Run/路径/版本身份。"""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._grants: dict[str, _GrantState] = {}
        self._lock = threading.RLock()

    @property
    def allowed_tools(self) -> frozenset[str]:
        return _ALLOWED_TOOLS

    def bind(
        self,
        runtime: CandidateRuntime,
        *,
        ttl_seconds: float = 300,
    ) -> ScopedToolGrant:
        if ttl_seconds <= 0:
            raise ValueError("Scoped Token 有效期必须为正数")
        token = secrets.token_urlsafe(32)
        expires_at = self._clock() + ttl_seconds
        with self._lock:
            self._grants[token] = _GrantState(
                runtime=runtime,
                expires_at=expires_at,
            )
        return ScopedToolGrant(token=token, expires_at=expires_at)

    def revoke(self, token: str) -> None:
        with self._lock:
            state = self._grants.get(token)
            if state is not None:
                state.revoked = True

    def call(
        self,
        token: str,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> GatewayToolResult:
        state, error = self._authorize(token, tool_name)
        if error is not None:
            return error
        assert state is not None
        try:
            if tool_name == "render_candidate":
                request = RenderCandidateInput.model_validate(arguments)
                result = state.runtime.render_candidate(request)
                preview = None
                latest = state.runtime.latest_candidate
                if result.ok and latest is not None:
                    preview = latest.preview_jpeg
                return GatewayToolResult(
                    result.model_dump(mode="json", exclude_none=True),
                    preview,
                )

            request = FinishCandidateInput.model_validate(arguments)
            result = state.runtime.finish_candidate(request)
            if result.ok:
                self.revoke(token)
            return GatewayToolResult(result.model_dump(mode="json", exclude_none=True))
        except ValidationError:
            return _failure(
                "invalid_arguments",
                "工具参数不符合契约",
                correctable=True,
            )

    def _authorize(
        self,
        token: str,
        tool_name: str,
    ) -> tuple[_GrantState | None, GatewayToolResult | None]:
        with self._lock:
            state = self._grants.get(token)
            if state is None:
                return None, _failure("token_invalid", "Scoped Token 无效")
            if state.revoked:
                return None, _failure("token_revoked", "Scoped Token 已撤销")
            if self._clock() >= state.expires_at:
                state.revoked = True
                return None, _failure("token_expired", "Scoped Token 已过期")
            if tool_name not in _ALLOWED_TOOLS:
                return None, _failure(
                    "tool_not_allowed",
                    "该工具不在本轮权限内",
                    correctable=True,
                )
            return state, None


def _failure(
    code: str,
    message: str,
    *,
    correctable: bool = False,
) -> GatewayToolResult:
    return GatewayToolResult(
        {
            "ok": False,
            "error": {
                "code": code,
                "message": message,
                "correctable": correctable,
            },
        }
    )
