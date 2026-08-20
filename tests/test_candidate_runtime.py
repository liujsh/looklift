"""受控候选 Runtime 的状态、安全与渲染闭环测试。"""

from __future__ import annotations

import io
from copy import deepcopy
from pathlib import Path

import pytest
from PIL import Image

from looklift.agent_tool_contract import (
    AgentTemplate,
    FinishCandidateInput,
    RenderCandidateInput,
    ScalarOperation,
)
from looklift.candidate_runtime import CandidateRuntime
from looklift.candidate_rendering import ProxyCandidateRenderer
from looklift.candidate_runtime_types import InMemoryRunAuthority, RunBinding


def _jpeg(color: tuple[int, int, int] = (128, 128, 128)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format="JPEG")
    return buffer.getvalue()


class FakeRenderer:
    def __init__(self, *, output: bytes | None = None, fail: bool = False) -> None:
        self.output = _jpeg() if output is None else output
        self.fail = fail
        self.calls: list[dict] = []
        self.after_render = None

    def render(self, _image_path: Path, analysis: dict) -> bytes:
        self.calls.append(deepcopy(analysis))
        if self.fail:
            raise RuntimeError("模拟渲染失败")
        if self.after_render is not None:
            self.after_render()
        return self.output


def _binding(max_render_calls: int = 3) -> RunBinding:
    return RunBinding(
        run_id="run-1",
        attempt_id="attempt-1",
        lease="lease-1",
        base_version_id="version-1",
        image_path=Path("private/original.jpg"),
        max_render_calls=max_render_calls,
    )


def _template() -> AgentTemplate:
    return AgentTemplate(
        template_id="portrait-soft",
        version=1,
        name="柔和人像",
        scene_tags=["portrait"],
        intent_tags=["soft"],
        expected_effect="降低反差并略微提亮",
        contraindications=[],
        risks=["背景可能变平"],
        compatible_skills=["portrait-natural"],
        operations=[
            ScalarOperation(
                path="basic.contrast",
                mode="delta",
                value=-10,
                reason="降低反差",
            ),
            ScalarOperation(
                path="basic.exposure",
                mode="set",
                value=1,
                reason="提亮起点",
            ),
        ],
    )


def _request(
    *operations: ScalarOperation,
    strength: float | None = None,
) -> RenderCandidateInput:
    return RenderCandidateInput(
        operations=list(operations),
        intent="生成自然候选",
        template_strength=strength,
    )


def _exposure_delta(value: float = 0.1) -> ScalarOperation:
    return ScalarOperation(
        path="basic.exposure",
        mode="delta",
        value=value,
        reason="测试曝光",
    )


def _runtime(
    sample_analysis: dict,
    *,
    template: AgentTemplate | None = None,
    renderer: FakeRenderer | None = None,
    max_render_calls: int = 3,
) -> tuple[CandidateRuntime, InMemoryRunAuthority, FakeRenderer]:
    binding = _binding(max_render_calls)
    authority = InMemoryRunAuthority(binding)
    selected_renderer = renderer or FakeRenderer()
    runtime = CandidateRuntime(
        binding=binding,
        authority=authority,
        baseline_analysis=sample_analysis,
        renderer=selected_renderer,
        template=template,
    )
    return runtime, authority, selected_renderer


@pytest.mark.parametrize(
    ("strength", "expected_contrast", "expected_exposure"),
    [(0.0, 20.0, 0.1), (0.5, 15.0, 0.6), (1.0, 10.0, 1.1)],
)
def test_template_is_relative_to_baseline_and_scaled(
    sample_analysis: dict,
    strength: float,
    expected_contrast: float,
    expected_exposure: float,
) -> None:
    baseline = deepcopy(sample_analysis)
    baseline["basic"]["contrast"] = 20
    baseline["basic"]["exposure"] = 0
    runtime, _, _ = _runtime(baseline, template=_template())

    result = runtime.render_candidate(_request(_exposure_delta(), strength=strength))

    assert result.ok is True
    revision = runtime.latest_candidate
    assert revision is not None
    assert revision.analysis["basic"]["contrast"] == expected_contrast
    assert revision.analysis["basic"]["exposure"] == pytest.approx(expected_exposure)
    assert baseline["basic"] == {**sample_analysis["basic"], "contrast": 20, "exposure": 0}


def test_template_can_only_be_decided_on_first_successful_candidate(
    sample_analysis: dict,
) -> None:
    runtime, _, _ = _runtime(sample_analysis, template=_template())
    first = runtime.render_candidate(_request(_exposure_delta()))

    second = runtime.render_candidate(_request(_exposure_delta(), strength=0.5))

    assert first.ok is True
    assert second.ok is False
    assert second.error is not None
    assert second.error.code == "template_already_decided"
    assert len(runtime.candidates) == 1


def test_template_strength_without_selected_template_is_rejected(
    sample_analysis: dict,
) -> None:
    runtime, _, renderer = _runtime(sample_analysis)

    result = runtime.render_candidate(_request(_exposure_delta(), strength=0.5))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "template_not_selected"
    assert renderer.calls == []


def test_out_of_range_delta_rejects_whole_patch_without_render(
    sample_analysis: dict,
) -> None:
    runtime, _, renderer = _runtime(sample_analysis)

    result = runtime.render_candidate(
        _request(
            _exposure_delta(0.2),
            ScalarOperation(
                path="basic.contrast",
                mode="delta",
                value=999,
                reason="越界",
            ),
        )
    )

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "invalid_patch"
    assert renderer.calls == []
    assert runtime.candidates == ()


def test_candidates_form_immutable_linear_chain(sample_analysis: dict) -> None:
    runtime, _, _ = _runtime(sample_analysis)
    first = runtime.render_candidate(_request(_exposure_delta(0.1)))
    second = runtime.render_candidate(_request(_exposure_delta(0.2)))

    assert first.ok and second.ok
    revisions = runtime.candidates
    assert revisions[1].parent_candidate_id == revisions[0].candidate_id
    exposed = revisions[0].analysis
    exposed["basic"]["exposure"] = 999
    assert revisions[0].analysis["basic"]["exposure"] != 999
    assert revisions[1].analysis["basic"]["exposure"] == pytest.approx(
        revisions[0].analysis["basic"]["exposure"] + 0.2
    )


def test_candidate_contains_real_jpeg_and_deterministic_metrics(
    sample_analysis: dict,
) -> None:
    runtime, _, _ = _runtime(
        sample_analysis,
        renderer=FakeRenderer(output=_jpeg((255, 255, 255))),
    )

    result = runtime.render_candidate(_request(_exposure_delta()))

    assert result.ok is True
    assert result.metrics is not None
    assert result.metrics.mean_luminance == pytest.approx(1)
    assert result.metrics.highlight_clip_ratio == pytest.approx(1)
    assert result.metrics.shadow_clip_ratio == pytest.approx(0)
    assert runtime.latest_candidate is not None
    assert runtime.latest_candidate.preview_jpeg.startswith(b"\xff\xd8")


def test_render_failure_preserves_previous_candidate(sample_analysis: dict) -> None:
    renderer = FakeRenderer()
    runtime, _, _ = _runtime(sample_analysis, renderer=renderer)
    first = runtime.render_candidate(_request(_exposure_delta()))
    renderer.fail = True

    failed = runtime.render_candidate(_request(_exposure_delta()))

    assert first.ok is True
    assert failed.ok is False
    assert failed.error is not None
    assert failed.error.code == "render_failed"
    assert len(runtime.candidates) == 1


def test_late_render_after_lease_rotation_cannot_create_candidate(
    sample_analysis: dict,
) -> None:
    renderer = FakeRenderer()
    runtime, authority, _ = _runtime(sample_analysis, renderer=renderer)
    renderer.after_render = lambda: authority.rotate_lease("lease-2")

    result = runtime.render_candidate(_request(_exposure_delta()))

    assert result.ok is False
    assert result.error is not None
    assert result.error.code == "stale"
    assert runtime.candidates == ()


def test_formal_baseline_change_marks_run_stale(sample_analysis: dict) -> None:
    runtime, authority, renderer = _runtime(sample_analysis)
    authority.change_base_version("version-2")

    result = runtime.render_candidate(_request(_exposure_delta()))

    assert result.error is not None
    assert result.error.code == "stale"
    assert renderer.calls == []


def test_proxy_renderer_reuses_safe_jpeg_pipeline(
    tmp_path: Path,
    sample_analysis: dict,
) -> None:
    photo = tmp_path / "source.jpg"
    exif = Image.Exif()
    exif[315] = "private-author"
    Image.new("RGB", (32, 24), (90, 120, 150)).save(photo, exif=exif)
    binding = RunBinding(
        run_id="run-real",
        attempt_id="attempt-real",
        lease="lease-real",
        base_version_id="version-real",
        image_path=photo,
    )
    runtime = CandidateRuntime(
        binding=binding,
        authority=InMemoryRunAuthority(binding),
        baseline_analysis=sample_analysis,
        renderer=ProxyCandidateRenderer(),
    )

    result = runtime.render_candidate(_request(_exposure_delta()))

    assert result.ok is True
    assert runtime.latest_candidate is not None
    with Image.open(io.BytesIO(runtime.latest_candidate.preview_jpeg)) as preview:
        assert preview.format == "JPEG"
        assert preview.getexif() == {}


def test_cancelled_run_and_render_budget_are_enforced(sample_analysis: dict) -> None:
    runtime, authority, renderer = _runtime(sample_analysis, max_render_calls=1)
    assert runtime.render_candidate(_request(_exposure_delta())).ok is True

    exhausted = runtime.render_candidate(_request(_exposure_delta()))
    authority.cancel()
    cancelled = runtime.render_candidate(_request(_exposure_delta()))

    assert exhausted.error is not None
    assert exhausted.error.code == "budget_exhausted"
    assert cancelled.error is not None
    assert cancelled.error.code == "cancelled"
    assert len(renderer.calls) == 1


def test_finish_candidate_validates_latest_candidate_and_is_single_use(
    sample_analysis: dict,
) -> None:
    runtime, _, _ = _runtime(sample_analysis)
    rendered = runtime.render_candidate(_request(_exposure_delta()))
    assert rendered.candidate_id is not None

    wrong = runtime.finish_candidate(
        FinishCandidateInput(
            outcome="candidate_ready",
            candidate_id="candidate-other",
            summary="错误引用",
            review_items=[],
            uncertainties=[],
            limitations=[],
        )
    )
    ready = runtime.finish_candidate(
        FinishCandidateInput(
            outcome="candidate_ready",
            candidate_id=rendered.candidate_id,
            summary="候选可复核",
            review_items=["高光"],
            uncertainties=[],
            limitations=[],
        )
    )
    repeated = runtime.finish_candidate(
        FinishCandidateInput(
            outcome="candidate_ready",
            candidate_id=rendered.candidate_id,
            summary="重复",
            review_items=[],
            uncertainties=[],
            limitations=[],
        )
    )

    assert wrong.error is not None
    assert wrong.error.code == "candidate_not_current"
    assert ready.ok is True
    assert repeated.error is not None
    assert repeated.error.code == "run_finished"


def test_no_change_and_insufficient_capability_can_finish_without_candidate(
    sample_analysis: dict,
) -> None:
    no_change_runtime, _, _ = _runtime(sample_analysis)
    no_change = no_change_runtime.finish_candidate(
        FinishCandidateInput(
            outcome="no_change_needed",
            summary="当前已经满足目标",
            review_items=[],
            uncertainties=[],
            limitations=[],
        )
    )
    insufficient_runtime, _, _ = _runtime(sample_analysis)
    insufficient = insufficient_runtime.finish_candidate(
        FinishCandidateInput(
            outcome="insufficient_capability",
            summary="需要局部蒙版",
            review_items=[],
            uncertainties=[],
            limitations=["仅支持全局参数"],
        )
    )

    assert no_change.ok is True
    assert insufficient.ok is True
