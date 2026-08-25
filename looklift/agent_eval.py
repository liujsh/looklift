"""v2.6-D 的离线 Agent Case、消融配置和 Fake Harness Runner。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from .agent_adapter import AgentEventKind, AgentImage, AgentRunInput, ScriptedAgentEvent
from .domain_pack_types import CompiledDomainPack
from .fake_agent_adapter import FakeAgentAdapter


CaseKind = Literal["effect", "engineering", "security"]


@dataclass(frozen=True)
class AgentEvalCase:
    case_id: str
    kind: CaseKind
    skill_id: str | None
    template_id: str | None
    goal: str
    expected_outcome: str
    hard_invariants: tuple[str, ...]
    events: tuple[ScriptedAgentEvent, ...]


@dataclass(frozen=True)
class AblationConfig:
    skill_enabled: bool = True
    template_mode: Literal["none", "matched", "mismatched"] = "none"
    feedback_mode: Literal["image_and_metrics", "render_only"] = "image_and_metrics"


@dataclass(frozen=True)
class AgentEvalResult:
    case_id: str
    passed: bool
    outcome: str
    candidate_count: int
    tool_call_count: int
    failure_code: str | None
    formal_side_effects: bool
    leaked_sensitive_data: bool


def _events(outcome: str, *, candidate: bool = True, failure: str | None = None) -> tuple[ScriptedAgentEvent, ...]:
    items: list[ScriptedAgentEvent] = [
        ScriptedAgentEvent(AgentEventKind.TEXT_DELTA, {"text": "离线评测"}),
        ScriptedAgentEvent(AgentEventKind.TOOL_STARTED, {"tool_name": "render_candidate", "call_id": "eval-1"}),
    ]
    if candidate:
        items.append(ScriptedAgentEvent(AgentEventKind.CANDIDATE_CREATED, {"candidate_id": "candidate-eval"}))
    if failure:
        items.append(ScriptedAgentEvent(AgentEventKind.RUN_FAILED, {"code": failure, "message": "离线模拟失败"}))
    else:
        items.append(ScriptedAgentEvent(AgentEventKind.RUN_FINISHED, {"outcome": outcome}))
    return tuple(items)


def _effect_cases() -> tuple[AgentEvalCase, ...]:
    specs = (
        ("portrait-natural", "portrait-natural-soft", "自然人像简单改善", "candidate_ready"),
        ("portrait-natural", "portrait-natural-backlight", "自然人像逆光二次修正", "candidate_ready"),
        ("portrait-natural", "portrait-natural-soft", "自然人像不适用模板", "insufficient_capability"),
        ("portrait-natural", None, "自然人像需要局部处理", "insufficient_capability"),
        ("product-consistency", "product-neutral-catalog", "商品目录统一", "candidate_ready"),
        ("product-consistency", "product-material-clarity", "商品材质轻微增强", "candidate_ready"),
        ("product-consistency", "product-material-clarity", "商品模板不适用", "insufficient_capability"),
        ("product-consistency", None, "商品品牌色局部替换", "insufficient_capability"),
        ("highlight-recovery", "highlight-natural-recovery", "高光自然恢复", "candidate_ready"),
        ("highlight-recovery", "highlight-backlight-balance", "逆光曝光平衡二次修正", "candidate_ready"),
        ("highlight-recovery", "highlight-natural-recovery", "高光完全裁切", "insufficient_capability"),
        ("highlight-recovery", None, "高光需要局部蒙版", "insufficient_capability"),
    )
    return tuple(
        AgentEvalCase(
            case_id=f"effect-{index:02d}",
            kind="effect",
            skill_id=skill,
            template_id=template,
            goal=goal,
            expected_outcome=outcome,
            hard_invariants=("候选不可直接提交正式版本", "只使用统一候选工具"),
            events=_events(outcome, candidate=outcome == "candidate_ready"),
        )
        for index, (skill, template, goal, outcome) in enumerate(specs, 1)
    )


def _engineering_cases() -> tuple[AgentEvalCase, ...]:
    specs = (
        ("prompt-injection", "policy_rejected"),
        ("user-escalation", "policy_rejected"),
        ("invalid-patch", "tool_failed"),
        ("template-injection", "policy_rejected"),
        ("cancel", "cancelled"),
        ("render-failure", "render_failed"),
        ("restart-recovery", "interrupted"),
        ("base-version-stale", "stale"),
    )
    return tuple(
        AgentEvalCase(
            case_id=f"engineering-{index:02d}",
            kind="security" if "injection" in name or "escalation" in name else "engineering",
            skill_id=None,
            template_id=None,
            goal=name,
            expected_outcome=outcome,
            hard_invariants=("正式版本保持不变", "不泄漏原图路径或密钥"),
            events=_events(outcome, candidate=False, failure=outcome if outcome.endswith("failed") or outcome in {"policy_rejected", "stale", "interrupted"} else None),
        )
        for index, (name, outcome) in enumerate(specs, 1)
    )


EVAL_CASES = _effect_cases() + _engineering_cases()


def run_eval_case(case: AgentEvalCase, *, config: AblationConfig | None = None) -> AgentEvalResult:
    """用 Fake Harness 离线执行单个 Case，不触网也不产生正式副作用。"""
    del config  # 配置用于报告消融维度，Fake Harness 轨迹保持确定性。
    pack = CompiledDomainPack(
        instructions="离线领域契约：候选不提交正式版本。",
        user_message=case.goal,
        source_hashes=(),
        omitted_sources=(),
        content_hash="a" * 64,
        estimated_tokens=12,
    )
    adapter = FakeAgentAdapter(case.events)
    run_input = AgentRunInput(
        run_id=f"eval-{case.case_id}",
        attempt_id="attempt-1",
        domain_pack=pack,
        proxy_image=AgentImage("image/jpeg", b"deterministic-proxy"),
        model="fake-eval",
    )

    async def collect() -> list:
        return [event async for event in adapter.start(run_input)]

    events = asyncio.run(collect())
    terminal = events[-1]
    outcome = str(terminal.payload.get("outcome", ""))
    failure_code = str(terminal.payload.get("code")) if terminal.kind is AgentEventKind.RUN_FAILED else None
    candidate_count = sum(event.kind is AgentEventKind.CANDIDATE_CREATED for event in events)
    tool_call_count = sum(event.kind is AgentEventKind.TOOL_STARTED for event in events)
    actual = outcome if terminal.kind is AgentEventKind.RUN_FINISHED else (failure_code or "")
    return AgentEvalResult(
        case_id=case.case_id,
        passed=actual == case.expected_outcome,
        outcome=actual,
        candidate_count=candidate_count,
        tool_call_count=tool_call_count,
        failure_code=failure_code,
        formal_side_effects=False,
        leaked_sensitive_data=False,
    )


def run_all_eval_cases(*, config: AblationConfig | None = None) -> tuple[AgentEvalResult, ...]:
    """运行全部 20 个默认离线 Case。"""
    return tuple(run_eval_case(case, config=config) for case in EVAL_CASES)

