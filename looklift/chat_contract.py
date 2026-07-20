"""AI 对话参数操作契约：白名单解析、范围限制与原子曲线替换。"""
from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from .render.contract import (
    ai_scalar_paths,
    param_bounds,
    param_default,
    resolve_path,
    tone_curve_contract,
)


@dataclass(frozen=True)
class ChatApplyResult:
    """一次模型响应经过本地契约规范化后的确定性结果。"""

    analysis: dict
    changes: tuple[dict, ...]
    rejected: tuple[dict, ...]


def apply_chat_operations(analysis: dict, operations: list[dict]) -> ChatApplyResult:
    """在 analysis 深拷贝上依次应用合法操作，绝不修改调用方对象。

    标量操作逐项接受或拒绝；主曲线作为一个整体校验，任一点非法都不落地。
    范围、白名单与曲线限制全部来自 ``render.contract``。
    """
    current = deepcopy(analysis)
    changes: list[dict] = []
    rejected: list[dict] = []

    if not isinstance(operations, list):
        return ChatApplyResult(
            current,
            (),
            ({"operation": deepcopy(operations), "reason": "参数操作必须是数组"},),
        )

    for operation in operations:
        if not isinstance(operation, dict):
            rejected.append(_rejection(operation, "参数操作必须是对象"))
            continue
        operation_type = operation.get("type")
        if operation_type == "scalar":
            change, reason = _apply_scalar(current, operation)
        elif operation_type == "tone_curve":
            change, reason = _apply_tone_curve(current, operation)
        else:
            change, reason = None, "未知操作类型"

        if change is not None:
            changes.append(change)
        else:
            rejected.append(_rejection(operation, reason or "操作未生效"))

    return ChatApplyResult(current, tuple(changes), tuple(rejected))


def _apply_scalar(analysis: dict, operation: dict) -> tuple[dict | None, str | None]:
    path = operation.get("path")
    if not isinstance(path, str) or path not in ai_scalar_paths():
        return None, "未知参数路径"

    mode = operation.get("mode")
    if mode not in {"delta", "set"}:
        return None, "未知标量操作模式"

    value = operation.get("value")
    if not _finite_number(value):
        return None, "参数值必须是有限数值"

    container, key = resolve_path(analysis, path)
    before = container.get(key, param_default(path))
    if not _finite_number(before):
        return None, "当前参数不是有限数值"

    requested = float(before) + float(value) if mode == "delta" else float(value)
    lower, upper = param_bounds(path)
    after = min(float(upper), max(float(lower), requested))
    if float(before) == after:
        return None, "操作未产生变化"

    container[key] = after
    return {
        "type": "scalar",
        "path": path,
        "before": before,
        "after": after,
        "reason": _reason(operation),
    }, None


def _apply_tone_curve(analysis: dict, operation: dict) -> tuple[dict | None, str | None]:
    points = operation.get("points")
    reason = _validate_tone_curve(points)
    if reason is not None:
        return None, reason

    before = deepcopy(analysis.get("tone_curve", []))
    after = deepcopy(points)
    if before == after:
        return None, "曲线操作未产生变化"

    analysis["tone_curve"] = after
    return {
        "type": "tone_curve",
        "path": "tone_curve",
        "before": before,
        "after": after,
        "reason": _reason(operation),
    }, None


def _validate_tone_curve(points: Any) -> str | None:
    rule = tone_curve_contract()
    if not isinstance(points, list):
        return "曲线控制点必须是数组"
    if not rule["min_items"] <= len(points) <= rule["max_items"]:
        return "曲线控制点数量超出允许范围"

    previous_input: float | None = None
    for point in points:
        if not isinstance(point, dict):
            return "曲线控制点必须是对象"
        input_value = point.get("input")
        output_value = point.get("output")
        if not _finite_number(input_value) or not _finite_number(output_value):
            return "曲线坐标必须是有限数值"
        if not rule["input_min"] <= input_value <= rule["input_max"]:
            return "曲线输入坐标越界"
        if not rule["output_min"] <= output_value <= rule["output_max"]:
            return "曲线输出坐标越界"
        if previous_input is not None and input_value <= previous_input:
            return "曲线输入坐标必须严格递增"
        previous_input = float(input_value)

    if points[0]["input"] != rule["input_min"] or points[-1]["input"] != rule["input_max"]:
        return "曲线必须包含完整的起止端点"
    return None


def _finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _reason(operation: dict) -> str:
    reason = operation.get("reason", "")
    return reason.strip() if isinstance(reason, str) else ""


def _rejection(operation: Any, reason: str) -> dict:
    return {"operation": deepcopy(operation), "reason": reason}
