"""强度缩放:把一份 100% 强度的 analysis 按滑杆比例缩放成 factor 强度。

供 GUI 的强度滑杆(U20)使用:滑杆变化 → `scale_analysis` → 同时喂给
`render.render`(预览)和 `xmp_writer`(导出)。纯函数,不做任何 I/O。

字段缩放规则见 docs/specs/v0.4/design.md「强度缩放语义」一节,与
`analyzer.ANALYSIS_SCHEMA` 逐字段对应。
"""
from __future__ import annotations

import copy
from typing import Any

_BASIC_FIELDS = (
    "temperature_shift", "tint_shift", "exposure", "contrast",
    "highlights", "shadows", "whites", "blacks",
    "texture", "clarity", "dehaze", "vibrance", "saturation",
)

_HSL_FIELDS = ("hue", "saturation", "luminance")

_CG_ZONES = ("shadows", "midtones", "highlights", "global_")
_CG_ZONE_FIELDS = ("saturation", "luminance")  # hue 是色轮绝对角度,不缩放

_EFFECTS_FIELDS = ("vignette_amount", "grain_amount")


def scale_analysis(analysis: dict[str, Any], factor: float) -> dict[str, Any]:
    """按强度 factor 缩放 analysis 里的调整幅度字段,返回新 dict(不修改入参)。

    factor 定义域 `[0.0, 1.0]`,对应 GUI 强度滑杆 0%-100%;越界值会被裁剪到
    该区间(防御性处理——调用方仍应在 API 层校验滑杆输入,这里的裁剪只是
    保证函数本身不会因越界输入产生离谱结果)。

    对缺失/残缺的分区做宽松处理(`.get` + 类型检查),不因局部字段缺失而
    抛 KeyError,容忍度与 `analyzer._normalize` 的输出形状一致。
    """
    factor = max(0.0, min(1.0, factor))
    result = copy.deepcopy(analysis)

    _scale_basic(result, factor)
    _scale_hsl(result, factor)
    _scale_color_grading(result, factor)
    _scale_effects(result, factor)
    result["tone_curve"] = _scale_tone_curve(result.get("tone_curve"), factor)

    return result


def _scale_basic(result: dict[str, Any], factor: float) -> None:
    basic = result.get("basic")
    if not isinstance(basic, dict):
        return
    for key in _BASIC_FIELDS:
        if key in basic:
            basic[key] = basic[key] * factor


def _scale_hsl(result: dict[str, Any], factor: float) -> None:
    for entry in result.get("hsl") or []:
        if not isinstance(entry, dict):
            continue
        for key in _HSL_FIELDS:
            if key in entry:
                entry[key] = entry[key] * factor


def _scale_color_grading(result: dict[str, Any], factor: float) -> None:
    cg = result.get("color_grading")
    if not isinstance(cg, dict):
        return
    for zone in _CG_ZONES:
        z = cg.get(zone)
        if not isinstance(z, dict):
            continue
        for key in _CG_ZONE_FIELDS:
            if key in z:
                z[key] = z[key] * factor
        # zone["hue"]:色轮绝对角度,不缩放
    if "balance" in cg:
        cg["balance"] = cg["balance"] * factor
    # cg["blending"]:中间调过渡范围的技术参数,不代表强度,不缩放


def _scale_effects(result: dict[str, Any], factor: float) -> None:
    effects = result.get("effects")
    if not isinstance(effects, dict):
        return
    for key in _EFFECTS_FIELDS:
        if key in effects:
            effects[key] = effects[key] * factor


def _scale_tone_curve(points: Any, factor: float) -> list[Any]:
    """向恒等线(output == input)插值:factor=0 退化为对角线,factor=1 等于原曲线。"""
    if not points:
        return []
    scaled = []
    for point in points:
        if not isinstance(point, dict) or "input" not in point or "output" not in point:
            scaled.append(point)
            continue
        new_point = dict(point)
        new_point["output"] = point["input"] + factor * (point["output"] - point["input"])
        scaled.append(new_point)
    return scaled
