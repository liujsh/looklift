"""Pydantic AI Provider 的显式构造边界，不执行自动切换。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from pydantic_ai.models import Model
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.anthropic import AnthropicProvider
from pydantic_ai.providers.openai import OpenAIProvider


ProviderKind = Literal["anthropic", "openai_compatible", "ollama"]


@dataclass(frozen=True)
class ApiModelConfig:
    """一次 Attempt 冻结的 API 模型配置。"""

    provider: ProviderKind
    model: str
    api_key: str | None = None
    base_url: str | None = None

    def __post_init__(self) -> None:
        if not self.model.strip():
            raise ValueError("模型名称不能为空")
        if self.provider in {"openai_compatible", "ollama"} and not self.base_url:
            raise ValueError("OpenAI-compatible 与 Ollama 必须显式提供 base_url")


def build_pydantic_model(config: ApiModelConfig) -> Model:
    """只构造指定 Provider；失败交还调用方，不静默降级。"""
    if config.provider == "anthropic":
        return AnthropicModel(
            config.model,
            provider=AnthropicProvider(
                api_key=config.api_key,
                base_url=config.base_url,
            ),
        )

    base_url = _openai_base_url(config.base_url or "")
    api_key = config.api_key
    if config.provider == "ollama" and not api_key:
        api_key = "ollama-local"
    return OpenAIChatModel(
        config.model,
        provider=OpenAIProvider(base_url=base_url, api_key=api_key),
    )


def _openai_base_url(value: str) -> str:
    value = value.rstrip("/")
    return value if value.endswith("/v1") else f"{value}/v1"
