"""参数契约:可调参数点路径枚举 + 机器可读范围 + 结构解析规则。

v2.0-A 拥有的跨 spec 单一真相源(D1):v2.0-B 右面板 min/max/复位、v2.1 delta
白名单/clamp 域/落点都从本模块导出,不各自手抄。刻意只依赖 analyzer.ANALYSIS_SCHEMA,
不 import numba/pyvips,使 chat 层导入它不触发引擎重编译。
"""
from __future__ import annotations

from ..analyzer import ANALYSIS_SCHEMA, _COLOR_KEYS


def param_paths() -> list[str]:
    """枚举所有可调数值参数的点路径,不含整点数组 tone_curve。"""
    return list(_path_nodes())


def param_bounds(path: str) -> tuple[float, float]:
    """从 schema 的 minimum/maximum 读取指定路径范围。"""
    try:
        node = _path_nodes()[path]
    except KeyError:
        raise KeyError(path) from None
    return node["minimum"], node["maximum"]


def param_default(path: str) -> float:
    """返回参数复位值；默认中性为 0，颜色分级混合的中性值为 50。"""
    if path not in _path_nodes():
        raise KeyError(path)
    return 50 if path == "color_grading.blending" else 0


def _path_nodes() -> dict[str, dict]:
    """从 schema 构造可调点路径到数值叶子的映射。"""
    props = ANALYSIS_SCHEMA["properties"]
    nodes: dict[str, dict] = {}

    for field, node in props["basic"]["properties"].items():
        if node.get("type") == "number":
            nodes[f"basic.{field}"] = node

    hsl_props = props["hsl"]["items"]["properties"]
    for color in _COLOR_KEYS:
        for field, node in hsl_props.items():
            if node.get("type") == "number":
                nodes[f"hsl.{color}.{field}"] = node

    for field, node in props["color_grading"]["properties"].items():
        if node.get("type") == "number":
            nodes[f"color_grading.{field}"] = node
        elif node.get("type") == "object":
            zone = "global" if field == "global_" else field
            for child, leaf in node["properties"].items():
                if leaf.get("type") == "number":
                    nodes[f"color_grading.{zone}.{child}"] = leaf

    for field, node in props["effects"]["properties"].items():
        if node.get("type") == "number":
            nodes[f"effects.{field}"] = node

    return nodes


def resolve_path(analysis: dict, path: str) -> tuple[dict, str]:
    """把点路径解析到 analysis 落点,返回 ``(container, key)``。

    hsl 按 color 段从数组查找,缺失时补零插入；color_grading.global 段映射
    到字典键 global_。
    """
    if path not in _path_nodes():
        raise KeyError(path)

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
        if len(parts) == 2:
            return color_grading, parts[1]
        key = "global_" if parts[1] == "global" else parts[1]
        zone = color_grading.setdefault(
            key, {"hue": 0, "saturation": 0, "luminance": 0}
        )
        return zone, parts[2]
    raise KeyError(path)
