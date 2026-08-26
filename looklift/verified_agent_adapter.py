"""为任意 Harness 统一追加候选 Verifier 与用户复核门。"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import asdict

from .agent_adapter import AgentAdapter, AgentEvent, AgentEventKind, AgentRunInput
from .candidate_runtime import CandidateRuntime
from .render.contract import param_paths
from .verifier import CandidateVerifier, UserReviewGate, critique


RuntimeResolver = Callable[[AgentRunInput], CandidateRuntime]


class CandidateReviewError(ValueError):
    def __init__(self, code: str, message: str, *, verifier: dict | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.verifier = verifier


def build_candidate_review(
    runtime: CandidateRuntime,
    *,
    verifier: CandidateVerifier,
    review_gate: UserReviewGate,
) -> dict:
    candidate = runtime.latest_candidate
    if candidate is None:
        raise CandidateReviewError("missing_candidate", "候选终态缺少候选")
    result = verifier.verify(candidate, allowed_paths=set(param_paths()))
    if result.hard_failed:
        raise CandidateReviewError(
            "verifier_failed",
            "候选未通过硬门禁",
            verifier=asdict(result),
        )
    review = review_gate.open(
        candidate, result, baseline_hash=runtime.binding.base_version_id
    )
    return {
        "verifier": asdict(result),
        "critique": critique(result),
        "user_review": asdict(review),
    }


class VerifiedAgentAdapter:
    def __init__(
        self,
        inner: AgentAdapter,
        *,
        runtime_resolver: RuntimeResolver,
        verifier: CandidateVerifier | None = None,
        review_gate: UserReviewGate | None = None,
    ) -> None:
        self._inner = inner
        self._runtime_resolver = runtime_resolver
        self._verifier = verifier or CandidateVerifier()
        self._review_gate = review_gate or UserReviewGate()

    async def start(self, run_input: AgentRunInput) -> AsyncIterator[AgentEvent]:
        runtime = self._runtime_resolver(run_input)
        async for event in self._inner.start(run_input):
            if (
                event.kind is not AgentEventKind.RUN_FINISHED
                or event.payload.get("outcome") != "candidate_ready"
            ):
                yield event
                continue
            try:
                review_payload = build_candidate_review(
                    runtime, verifier=self._verifier, review_gate=self._review_gate
                )
            except CandidateReviewError as exc:
                yield AgentEvent(
                    AgentEventKind.RUN_FAILED,
                    event.run_id,
                    event.attempt_id,
                    event.sequence,
                    {
                        "code": exc.code,
                        "message": str(exc),
                        "verifier": exc.verifier,
                    },
                )
                continue
            payload = dict(event.payload)
            payload.update(review_payload)
            yield AgentEvent(
                event.kind,
                event.run_id,
                event.attempt_id,
                event.sequence,
                payload,
            )

    async def cancel(self, run_id: str) -> None:
        await self._inner.cancel(run_id)

    async def dispose(self, run_id: str) -> None:
        await self._inner.dispose(run_id)
