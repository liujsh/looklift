"""不产生正式副作用的受控候选 Runtime。"""

from __future__ import annotations

import json
import threading
import uuid
from copy import deepcopy

from .agent_tool_contract import (
    AgentTemplate,
    FinishCandidateInput,
    FinishCandidateResult,
    ParameterChange,
    RenderCandidateInput,
    RenderCandidateResult,
    ScalarOperation,
    ToolFailure,
)
from .candidate_rendering import candidate_metrics
from .candidate_runtime_types import (
    CandidateRenderer,
    CandidateRevision,
    RunAuthority,
    RunBinding,
)
from .chat_contract import apply_chat_operations
from .render.contract import param_bounds, param_default, resolve_path


class CandidateRuntime:
    """拥有单个 Attempt 的预算、候选链和模型终态。"""

    def __init__(
        self,
        *,
        binding: RunBinding,
        authority: RunAuthority,
        baseline_analysis: dict,
        renderer: CandidateRenderer,
        template: AgentTemplate | None = None,
    ) -> None:
        self.binding = binding
        self._authority = authority
        self._baseline = deepcopy(baseline_analysis)
        self._renderer = renderer
        self._template = template
        self._candidates: list[CandidateRevision] = []
        self._render_calls = 0
        self._finished: FinishCandidateResult | None = None
        self._lock = threading.RLock()

    @property
    def candidates(self) -> tuple[CandidateRevision, ...]:
        return tuple(self._candidates)

    @property
    def latest_candidate(self) -> CandidateRevision | None:
        return self._candidates[-1] if self._candidates else None

    @property
    def finished(self) -> FinishCandidateResult | None:
        return self._finished

    def cancel(self) -> None:
        """先撤销领域 Lease 权威，Harness 中止即使晚到也不能落候选。"""
        self._authority.cancel(self.binding)

    def render_candidate(self, request: RenderCandidateInput) -> RenderCandidateResult:
        with self._lock:
            return self._render_candidate(request)

    def _render_candidate(self, request: RenderCandidateInput) -> RenderCandidateResult:
        guard_error = self._authority.validate(self.binding)
        if guard_error is not None:
            return self._render_failure(guard_error, _guard_message(guard_error), False)
        if self._finished is not None:
            return self._render_failure("run_finished", "本轮已经结束", False)
        if self._render_calls >= self.binding.max_render_calls:
            return self._render_failure("budget_exhausted", "候选渲染预算已耗尽", False)
        self._render_calls += 1

        template_error = self._validate_template_request(request)
        if template_error is not None:
            return self._render_failure(*template_error)

        base = self.latest_candidate.analysis if self.latest_candidate else deepcopy(self._baseline)
        operations = self._template_operations(base, request.template_strength)
        operations.extend(request.operations)
        applied, changes, patch_error = _apply_strict_operations(base, operations)
        if patch_error is not None:
            return self._render_failure("invalid_patch", patch_error, True)
        if not changes:
            return self._render_failure("no_effect", "参数操作未产生可见候选变化", True)

        try:
            preview = self._renderer.render(self.binding.image_path, applied)
            metrics = candidate_metrics(preview)
        except Exception:
            return self._render_failure("render_failed", "候选渲染失败", True)

        parent = self.latest_candidate
        revision = CandidateRevision(
            candidate_id=f"candidate-{uuid.uuid4().hex}",
            parent_candidate_id=parent.candidate_id if parent else None,
            _analysis_json=json.dumps(
                applied,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
            preview_jpeg=bytes(preview),
            metrics=metrics,
            _changes_json=json.dumps(
                [change.model_dump(mode="json") for change in changes],
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
        )
        guard_error, _ = self._authority.commit_if_current(
            self.binding,
            lambda: self._candidates.append(revision),
        )
        if guard_error is not None:
            return self._render_failure(guard_error, _guard_message(guard_error), False)
        return RenderCandidateResult(
            ok=True,
            candidate_id=revision.candidate_id,
            parent_candidate_id=revision.parent_candidate_id,
            changes=revision.changes,
            metrics=metrics,
            warnings=(),
            remaining_render_calls=self._remaining_calls,
        )

    def finish_candidate(self, request: FinishCandidateInput) -> FinishCandidateResult:
        with self._lock:
            return self._finish_candidate(request)

    def _finish_candidate(self, request: FinishCandidateInput) -> FinishCandidateResult:
        guard_error = self._authority.validate(self.binding)
        if guard_error is not None:
            return _finish_failure(guard_error, _guard_message(guard_error), False)
        if self._finished is not None:
            return _finish_failure("run_finished", "本轮已经结束", False)
        latest = self.latest_candidate
        if request.outcome == "candidate_ready" and (
            latest is None or request.candidate_id != latest.candidate_id
        ):
            return _finish_failure(
                "candidate_not_current",
                "candidate_ready 必须引用最新成功候选",
                True,
            )
        if request.outcome == "no_change_needed" and latest is not None:
            return _finish_failure(
                "candidate_exists",
                "已有候选时不能声明无需修改",
                True,
            )
        result = FinishCandidateResult(
            ok=True,
            outcome=request.outcome,
            candidate_id=request.candidate_id,
            summary=request.summary,
            review_items=request.review_items,
            uncertainties=request.uncertainties,
            limitations=request.limitations,
        )
        guard_error, _ = self._authority.commit_if_current(
            self.binding,
            lambda: setattr(self, "_finished", result),
        )
        if guard_error is not None:
            return _finish_failure(guard_error, _guard_message(guard_error), False)
        return result

    def _validate_template_request(
        self,
        request: RenderCandidateInput,
    ) -> tuple[str, str, bool] | None:
        if request.template_strength is not None and self._template is None:
            return "template_not_selected", "本轮没有选择 Template", True
        if self._candidates and request.template_strength is not None:
            return "template_already_decided", "Template 只能在首个候选中决定", True
        return None

    def _template_operations(
        self,
        base: dict,
        strength: float | None,
    ) -> list[ScalarOperation]:
        if self._template is None or strength is None or strength == 0:
            return []
        scaled: list[ScalarOperation] = []
        snapshot = deepcopy(base)
        for operation in self._template.operations:
            value = operation.value * strength
            if operation.mode == "set":
                container, key = resolve_path(snapshot, operation.path)
                before = container.get(key, param_default(operation.path))
                value = float(before) + (operation.value - float(before)) * strength
            scaled.append(operation.model_copy(update={"value": value}))
            applied, _, error = _apply_strict_operations(snapshot, [scaled[-1]])
            if error is None:
                snapshot = applied
        return scaled

    @property
    def _remaining_calls(self) -> int:
        return max(0, self.binding.max_render_calls - self._render_calls)

    def _render_failure(
        self,
        code: str,
        message: str,
        correctable: bool,
    ) -> RenderCandidateResult:
        return RenderCandidateResult(
            ok=False,
            remaining_render_calls=self._remaining_calls,
            error=ToolFailure(
                code=code,
                message=message,
                correctable=correctable,
            ),
        )


def _apply_strict_operations(
    base: dict,
    operations: list,
) -> tuple[dict, list[ParameterChange], str | None]:
    current = deepcopy(base)
    changes: list[ParameterChange] = []
    for operation in operations:
        if isinstance(operation, ScalarOperation):
            container, key = resolve_path(current, operation.path)
            before = container.get(key, param_default(operation.path))
            requested = (
                float(before) + operation.value
                if operation.mode == "delta"
                else operation.value
            )
            lower, upper = param_bounds(operation.path)
            if not lower <= requested <= upper:
                return base, [], f"参数 {operation.path} 的结果超出允许范围"
        result = apply_chat_operations(current, [operation.model_dump(mode="python")])
        if result.rejected:
            return base, [], str(result.rejected[0]["reason"])
        current = result.analysis
        changes.extend(ParameterChange(**change) for change in result.changes)
    return current, changes, None


def _guard_message(code: str) -> str:
    return "本轮已经取消" if code == "cancelled" else "运行身份或正式基线已经变化"


def _finish_failure(
    code: str,
    message: str,
    correctable: bool,
) -> FinishCandidateResult:
    return FinishCandidateResult(
        ok=False,
        error=ToolFailure(code=code, message=message, correctable=correctable),
    )
