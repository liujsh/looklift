"""本地 CLI 与内嵌 API Harness 共用的最小 Adapter ABI。"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from .domain_pack_types import CompiledDomainPack


_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_SAFE_IMAGE_MEDIA_TYPES = frozenset({"image/jpeg"})


class AgentAdapterError(RuntimeError):
    """Adapter 生命周期或事件协议不合法。"""


class AgentEventKind(StrEnum):
    """所有 Harness 必须归一化到的有限事件集合。"""

    RUN_STARTED = "run_started"
    TEXT_DELTA = "text_delta"
    TOOL_STARTED = "tool_started"
    TOOL_COMPLETED = "tool_completed"
    CANDIDATE_CREATED = "candidate_created"
    USAGE_UPDATED = "usage_updated"
    CONTEXT_COMPACTION = "context_compaction"
    RUN_FINISHED = "run_finished"
    RUN_FAILED = "run_failed"

    @property
    def terminal(self) -> bool:
        return self in {self.RUN_FINISHED, self.RUN_FAILED}


@dataclass(frozen=True)
class AgentImage:
    """已脱敏的代理图；Adapter 不接收原图路径。"""

    media_type: str
    content: bytes

    def __post_init__(self) -> None:
        if self.media_type not in _SAFE_IMAGE_MEDIA_TYPES:
            raise ValueError("代理图媒体类型不受支持")
        if not isinstance(self.content, bytes) or not self.content:
            raise ValueError("代理图内容必须是非空字节串")


@dataclass(frozen=True)
class AgentRunInput:
    """一次 Harness Attempt 冻结后的最小输入。"""

    run_id: str
    attempt_id: str
    domain_pack: CompiledDomainPack
    proxy_image: AgentImage
    model: str

    def __post_init__(self) -> None:
        _require_text(self.run_id, "run_id")
        _require_text(self.attempt_id, "attempt_id")
        if not isinstance(self.domain_pack, CompiledDomainPack):
            raise ValueError("domain_pack 必须是编译后的 Domain Pack")
        if (
            not self.domain_pack.instructions.strip()
            or not self.domain_pack.user_message.strip()
        ):
            raise ValueError("Domain Prompt 与用户目标不能为空")
        if not _SHA256_PATTERN.fullmatch(self.domain_pack.content_hash):
            raise ValueError("Domain Pack Hash 必须是小写 SHA-256")
        _require_text(self.model, "model")


@dataclass(frozen=True)
class ScriptedAgentEvent:
    """Fake Harness 的无身份事件，由 Adapter 绑定 Attempt 和序号。"""

    kind: AgentEventKind
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, AgentEventKind):
            raise ValueError("事件类型不在统一协议内")
        if not isinstance(self.payload, Mapping):
            raise ValueError("事件 payload 必须是对象")
        object.__setattr__(self, "payload", dict(self.payload))


@dataclass(frozen=True)
class AgentEvent:
    """带 Run/Attempt 身份和单调序号的归一事件。"""

    kind: AgentEventKind
    run_id: str
    attempt_id: str
    sequence: int
    payload: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, AgentEventKind):
            raise ValueError("事件类型不在统一协议内")
        _require_text(self.run_id, "run_id")
        _require_text(self.attempt_id, "attempt_id")
        if self.sequence < 1:
            raise ValueError("事件序号必须是正整数")
        if not isinstance(self.payload, Mapping):
            raise ValueError("事件 payload 必须是对象")
        object.__setattr__(self, "payload", dict(self.payload))


class AgentAdapter(Protocol):
    """Harness 可替换边界；领域状态与正式副作用不属于此接口。"""

    def start(self, run_input: AgentRunInput) -> AsyncIterator[AgentEvent]: ...

    async def cancel(self, run_id: str) -> None: ...

    async def dispose(self, run_id: str) -> None: ...


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} 不能为空")
