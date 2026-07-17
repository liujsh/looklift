"""参数契约:可调参数点路径枚举 + 机器可读范围 + 结构解析规则。

v2.0-A 拥有的跨 spec 单一真相源(D1):v2.0-B 右面板 min/max/复位、v2.1 delta
白名单/clamp 域/落点都从本模块导出,不各自手抄。刻意只依赖 analyzer.ANALYSIS_SCHEMA,
不 import numba/pyvips,使 chat 层导入它不触发引擎重编译。
"""
from __future__ import annotations

from ..analyzer import ANALYSIS_SCHEMA, _COLOR_KEYS

_BASIC_FIELDS = (
    "temperature_shift", "tint_shift", "exposure", "contrast",
    "highlights", "shadows", "whites", "blacks",
    "texture", "clarity", "dehaze", "vibrance", "saturation",
)
_HSL_FIELDS = ("hue", "saturation", "luminance")
_CG_ZONES = ("shadows", "midtones", "highlights", "global")
_CG_ZONE_FIELDS = ("hue", "saturation", "luminance")
_CG_SCALARS = ("blending", "balance")
_EFFECTS_FIELDS = ("vignette_amount", "grain_amount")


def param_paths() -> list[str]:
    """枚举所有可调数值参数的点路径,不含整点数组 tone_curve。"""
    paths: list[str] = [f"basic.{field}" for field in _BASIC_FIELDS]
    for color in _COLOR_KEYS:
        paths += [f"hsl.{color}.{field}" for field in _HSL_FIELDS]
    for zone in _CG_ZONES:
        paths += [f"color_grading.{zone}.{field}" for field in _CG_ZONE_FIELDS]
    paths += [f"color_grading.{scalar}" for scalar in _CG_SCALARS]
    paths += [f"effects.{field}" for field in _EFFECTS_FIELDS]
    return paths


def param_bounds(path: str) -> tuple[float, float]:
    """从 schema 的 minimum/maximum 读取指定路径范围。"""
    node = _schema_node(path)
    return node["minimum"], node["maximum"]


def _schema_node(path: str) -> dict:
    props = ANALYSIS_SCHEMA["properties"]
    parts = path.split(".")
    section = parts[0]
    if section == "basic":
        return props["basic"]["properties"][parts[1]]
    if section == "effects":
        return props["effects"]["properties"][parts[1]]
    if section == "hsl":
        return props["hsl"]["items"]["properties"][parts[2]]
    if section == "color_grading":
        cg = props["color_grading"]["properties"]
        if parts[1] in _CG_SCALARS:
            return cg[parts[1]]
        key = "global_" if parts[1] == "global" else parts[1]
        return cg[key]["properties"][parts[2]]
    raise KeyError(path)


def resolve_path(analysis: dict, path: str) -> tuple[dict, str]:
    """把点路径解析到 analysis 落点,返回 ``(container, key)``。

    hsl 按 color 段从数组查找,缺失时补零插入；color_grading.global 段映射
    到字典键 global_。
    """
    parts = path.split(".")
    section = parts[0]
    if section == "basic":
        return analysis.setdefault("basic", {}), parts[1]
    if section == "effects":
        return analysis.setdefault("effects", {}), parts[1]
    if section == "hsl":
        color, field = parts[1], parts[2]
        items = analysis.setdefault("hsl", [])
        for item in items:
            if item.get("color") == color:
                return item, field
        item = {"color": color, "hue": 0, "saturation": 0, "luminance": 0}
        items.append(item)
        return item, field
    if section == "color_grading":
        color_grading = analysis.setdefault("color_grading", {})
        if parts[1] in _CG_SCALARS:
            return color_grading, parts[1]
        key = "global_" if parts[1] == "global" else parts[1]
        zone = color_grading.setdefault(
            key, {"hue": 0, "saturation": 0, "luminance": 0}
        )
        return zone, parts[2]
    raise KeyError(path)
