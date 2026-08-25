"""API Provider 只做离线构造，不发送真实请求。"""

from __future__ import annotations

import pytest
from pydantic_ai.models.anthropic import AnthropicModel
from pydantic_ai.models.openai import OpenAIChatModel

from looklift.pydantic_models import ApiModelConfig, build_pydantic_model


def test_build_anthropic_model_without_network() -> None:
    model = build_pydantic_model(
        ApiModelConfig(
            provider="anthropic",
            model="claude-test",
            api_key="test-key",
        )
    )

    assert isinstance(model, AnthropicModel)


@pytest.mark.parametrize("provider", ["openai_compatible", "ollama"])
def test_build_openai_compatible_models_without_network(provider: str) -> None:
    model = build_pydantic_model(
        ApiModelConfig(
            provider=provider,  # type: ignore[arg-type]
            model="local-test",
            base_url="http://127.0.0.1:11434",
        )
    )

    assert isinstance(model, OpenAIChatModel)
    assert str(model.base_url) == "http://127.0.0.1:11434/v1/"


def test_openai_compatible_requires_explicit_base_url() -> None:
    with pytest.raises(ValueError, match="base_url"):
        ApiModelConfig(provider="openai_compatible", model="test")
