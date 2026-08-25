"""v2.6 候选工具、相对 Template 与模型终态的单一数据契约。"""

from __future__ import annotations

import re
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .render.contract import ai_scalar_paths, param_bounds, tone_curve_contract


_SCALAR_PATHS = ai_scalar_paths()
_TONE_CURVE = tone_curve_contract()
_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class _ContractModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        allow_inf_nan=False,
        str_strip_whitespace=True,
    )


class CurvePoint(_ContractModel):
    """主明度曲线的单个控制点。"""

    input: float = Field(
        ge=_TONE_CURVE["input_min"],
        le=_TONE_CURVE["input_max"],
    )
    output: float = Field(
        ge=_TONE_CURVE["output_min"],
        le=_TONE_CURVE["output_max"],
    )


class ScalarOperation(_ContractModel):
    """白名单标量参数的相对或绝对修改。"""

    type: Literal["scalar"] = "scalar"
    path: str = Field(json_schema_extra={"enum": list(_SCALAR_PATHS)})
    mode: Literal["delta", "set"]
    value: float
    reason: str = Field(min_length=1, max_length=240)

    @field_validator("path")
    @classmethod
    def _known_path(cls, value: str) -> str:
        if value not in _SCALAR_PATHS:
            raise ValueError("未知参数路径")
        return value

    @model_validator(mode="after")
    def _set_value_in_range(self) -> ScalarOperation:
        if self.mode == "set":
            lower, upper = param_bounds(self.path)
            if not lower <= self.value <= upper:
                raise ValueError("set 值超出参数范围")
        return self


class ToneCurveOperation(_ContractModel):
    """原子替换主明度曲线。"""

    type: Literal["tone_curve"] = "tone_curve"
    points: tuple[CurvePoint, ...] = Field(
        min_length=int(_TONE_CURVE["min_items"]),
        max_length=int(_TONE_CURVE["max_items"]),
    )
    reason: str = Field(min_length=1, max_length=240)

    @model_validator(mode="after")
    def _valid_curve(self) -> ToneCurveOperation:
        inputs = [point.input for point in self.points]
        if any(current <= previous for previous, current in zip(inputs, inputs[1:])):
            raise ValueError("曲线输入坐标必须严格递增")
        if (
            inputs[0] != _TONE_CURVE["input_min"]
            or inputs[-1] != _TONE_CURVE["input_max"]
        ):
            raise ValueError("曲线必须包含完整起止端点")
        return self


EditOperation = Annotated[
    ScalarOperation | ToneCurveOperation,
    Field(discriminator="type"),
]


class RenderCandidateInput(_ContractModel):
    """模型可见的候选渲染请求，不含任何运行身份或路径。"""

    operations: tuple[EditOperation, ...] = Field(max_length=32)
    intent: str = Field(min_length=1, max_length=500)
    template_strength: float | None = Field(default=None, ge=0, le=1)


class AgentTemplate(_ContractModel):
    """相对正式基线、仅首候选可用的标量参数先验。"""

    template_id: str
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=80)
    scene_tags: tuple[str, ...]
    intent_tags: tuple[str, ...]
    expected_effect: str = Field(min_length=1, max_length=500)
    contraindications: tuple[str, ...]
    risks: tuple[str, ...]
    compatible_skills: tuple[str, ...]
    operations: tuple[ScalarOperation, ...] = Field(min_length=1, max_length=32)

    @field_validator("template_id")
    @classmethod
    def _valid_id(cls, value: str) -> str:
        if not _ID_PATTERN.fullmatch(value):
            raise ValueError("Template ID 必须是小写 hyphen-case")
        return value


class FinishCandidateInput(_ContractModel):
    """模型唯一允许产生的三种成功终态。"""

    outcome: Literal[
        "candidate_ready",
        "no_change_needed",
        "insufficient_capability",
    ]
    candidate_id: str | None = None
    summary: str = Field(min_length=1, max_length=1000)
    review_items: tuple[str, ...] = Field(max_length=12)
    uncertainties: tuple[str, ...] = Field(max_length=12)
    limitations: tuple[str, ...] = Field(max_length=12)

    @model_validator(mode="after")
    def _outcome_fields(self) -> FinishCandidateInput:
        if self.outcome == "candidate_ready" and not self.candidate_id:
            raise ValueError("candidate_ready 必须提供 candidate_id")
        if self.outcome != "candidate_ready" and self.candidate_id is not None:
            raise ValueError("非候选终态不能提供 candidate_id")
        if self.outcome == "insufficient_capability" and not self.limitations:
            raise ValueError("insufficient_capability 必须提供 limitations")
        return self


class ToolFailure(_ContractModel):
    """可回灌模型的稳定领域错误。"""

    code: str
    message: str
    correctable: bool


class ParameterChange(_ContractModel):
    """候选相对父版本的白盒参数差异。"""

    type: Literal["scalar", "tone_curve"]
    path: str
    before: Any
    after: Any
    reason: str


class CandidateMetrics(_ContractModel):
    """本地可确定计算的基础画面指标。"""

    mean_luminance: float = Field(ge=0, le=1)
    shadow_clip_ratio: float = Field(ge=0, le=1)
    highlight_clip_ratio: float = Field(ge=0, le=1)


class RenderCandidateResult(_ContractModel):
    """render_candidate 的 JSON 部分；预览图由 Harness 另附。"""

    ok: bool
    candidate_id: str | None = None
    parent_candidate_id: str | None = None
    changes: tuple[ParameterChange, ...] = ()
    metrics: CandidateMetrics | None = None
    warnings: tuple[str, ...] = ()
    remaining_render_calls: int = Field(ge=0)
    error: ToolFailure | None = None


class FinishCandidateResult(_ContractModel):
    """经 Runtime 核对后的模型终态。"""

    ok: bool
    outcome: str | None = None
    candidate_id: str | None = None
    summary: str = ""
    review_items: tuple[str, ...] = ()
    uncertainties: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    error: ToolFailure | None = None
