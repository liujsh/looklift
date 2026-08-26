"""API Harness 使用的版本化 Provider 配置快照。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ProviderProtocol(StrEnum):
    """首批 Provider 请求协议。"""

    OPENAI_CHAT_COMPLETIONS = "openai_chat_completions"
    OPENAI_RESPONSES = "openai_responses"
    OLLAMA_OPENAI_COMPATIBLE = "ollama_openai_compatible"


@dataclass(frozen=True)
class ProviderSnapshot:
    """一次 Attempt 冻结的非明文 Provider 配置。"""

    provider_id: str
    base_url: str
    model: str
    api_key_ref: str | None
    protocol: ProviderProtocol
    max_tokens: int
    config_version: int

    def __post_init__(self) -> None:
        for label, value in (
            ("provider_id", self.provider_id),
            ("base_url", self.base_url),
            ("model", self.model),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{label} 不能为空")
        try:
            protocol = ProviderProtocol(self.protocol)
        except ValueError as exc:
            raise ValueError("Provider 协议不受支持") from exc
        object.__setattr__(self, "protocol", protocol)
        if not isinstance(self.max_tokens, int) or self.max_tokens < 1:
            raise ValueError("最大 Token 必须是正整数")
        if not isinstance(self.config_version, int) or self.config_version < 1:
            raise ValueError("Provider 配置版本必须是正整数")
        if self.api_key_ref is not None and not self.api_key_ref.startswith(
            ("credential://", "dpapi://")
        ):
            raise ValueError("API Key 必须使用受控凭据引用")
        if (
            protocol is not ProviderProtocol.OLLAMA_OPENAI_COMPATIBLE
            and self.api_key_ref is None
        ):
            raise ValueError("远程 Provider 必须声明凭据引用")
