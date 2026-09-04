"""从会话/照片装配 Attempt 运行所需组件（spec 8.1）。

本模块把一次 Attempt 运行所需的 `CandidateRuntime`、`ProviderSnapshot` 解析器、
凭据解析器与 `OpenAiApiAdapter` 工厂组装起来，使真实 `openai-api` Adapter 工厂
能注入到 `gui.agent_stream` 的 Factory 表。候选 Runtime 使用内存权威与现有
代理渲染链，不产生正式副作用；基线/图片/版本来自调用方提供的会话事实。
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Any

from .agent_adapter import AgentRunInput
from .candidate_runtime import CandidateRuntime
from .candidate_runtime_types import InMemoryRunAuthority, RunBinding
from .candidate_rendering import ProxyCandidateRenderer
from .openai_api_adapter import OpenAiApiAdapter, OpenAiTransport
from .openai_http_transport import HttpxOpenAiTransport
from .provider_config_store import ProviderConfigStore
from .provider_snapshot import ProviderSnapshot

SnapshotResolver = Callable[[AgentRunInput], ProviderSnapshot]
CredentialResolver = Callable[[str], str | None]
RuntimeResolver = Callable[[AgentRunInput], CandidateRuntime]

_LEASE_PREFIX = "lease-"


def build_candidate_runtime(
    run_input: AgentRunInput,
    *,
    baseline_analysis: dict[str, Any],
    image_path: str | Path,
    base_version_id: str,
    max_render_calls: int = 3,
) -> CandidateRuntime:
    """为一次 Attempt 构造受控候选 Runtime（不产生正式副作用）。"""
    binding = RunBinding(
        run_id=run_input.run_id,
        attempt_id=run_input.attempt_id,
        lease=f"{_LEASE_PREFIX}{uuid.uuid4().hex}",
        base_version_id=base_version_id,
        image_path=Path(image_path),
        max_render_calls=max_render_calls,
    )
    authority = InMemoryRunAuthority(binding)
    renderer = ProxyCandidateRenderer()
    return CandidateRuntime(
        binding=binding,
        authority=authority,
        baseline_analysis=baseline_analysis,
        renderer=renderer,
    )


def make_openai_adapter_factory(
    *,
    snapshot_resolver: SnapshotResolver,
    credential_resolver: CredentialResolver,
    baseline_analysis: dict[str, Any],
    image_path: str | Path,
    base_version_id: str,
    transport: OpenAiTransport | None = None,
    max_render_calls: int = 3,
) -> Callable[[], OpenAiApiAdapter]:
    """构造 `openai-api` 的 Adapter 工厂；解析器可注入 fake 以便离线测试。"""
    if not baseline_analysis:
        raise ValueError("baseline_analysis 不能为空")
    if not base_version_id:
        raise ValueError("base_version_id 不能为空")

    def factory() -> OpenAiApiAdapter:
        def runtime_resolver(run_input: AgentRunInput) -> CandidateRuntime:
            return build_candidate_runtime(
                run_input,
                baseline_analysis=baseline_analysis,
                image_path=image_path,
                base_version_id=base_version_id,
                max_render_calls=max_render_calls,
            )

        return OpenAiApiAdapter(
            snapshot_resolver=snapshot_resolver,
            credential_resolver=credential_resolver,
            runtime_resolver=runtime_resolver,
            transport=transport or HttpxOpenAiTransport(),
        )

    return factory


def wire_openai_adapter_factory(
    provider_store: ProviderConfigStore,
    *,
    baseline_analysis: dict[str, Any],
    image_path: str | Path,
    base_version_id: str,
    max_render_calls: int = 3,
) -> Callable[[], OpenAiApiAdapter]:
    """把 ProviderConfigStore 绑定为快照/凭据解析器，生成真实工厂。"""

    def snapshot_resolver(run_input: AgentRunInput) -> ProviderSnapshot:
        snapshot = provider_store.load()
        if snapshot is None:
            raise ValueError("未保存 Provider 配置")
        if run_input.model and run_input.model != snapshot.model:
            return replace(snapshot, model=run_input.model)
        return snapshot

    def credential_resolver(reference: str) -> str | None:
        if reference is None:
            return None
        return provider_store.credentials.get(reference)

    return make_openai_adapter_factory(
        snapshot_resolver=snapshot_resolver,
        credential_resolver=credential_resolver,
        baseline_analysis=baseline_analysis,
        image_path=image_path,
        base_version_id=base_version_id,
        max_render_calls=max_render_calls,
    )
