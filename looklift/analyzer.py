"""从成片(可选:对照原片)逆向推断 Lightroom 调整参数。

两种后端:
- "cli": 调用本地 Claude Code CLI(`claude -p`),走 Claude Code 登录额度,无需 API key
- "api": 调用 Anthropic API(需要 API key),有结构化输出保证
- "auto": config.toml 显式指定 provider 时优先;否则有 API key(环境变量或 config.toml)
  则用 api,没有则退回本地 claude CLI
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import providers
from .providers import MODEL, MAX_EDGE, _extract_json  # 兼容旧引用

_COLOR_KEYS = ["red", "orange", "yellow", "green", "aqua", "blue", "purple", "magenta"]

_HUE_SAT_LUM = {
    "type": "object",
    "properties": {
        "hue": {"type": "number", "minimum": 0, "maximum": 360, "description": "色相角度 0-360,0 表示未着色"},
        "saturation": {"type": "number", "minimum": 0, "maximum": 100, "description": "饱和度 0 到 100"},
        "luminance": {"type": "number", "minimum": -100, "maximum": 100, "description": "明亮度 -100 到 100"},
    },
    "required": ["hue", "saturation", "luminance"],
    "additionalProperties": False,
}

ANALYSIS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {
            "type": "string",
            "description": "对这张照片后期风格的整体分析,用中文,包括色调倾向、影调结构、可能的拍摄/后期思路",
        },
        "steps": {
            "type": "array",
            "items": {"type": "string"},
            "description": "按顺序列出复现这种风格的后期步骤,用中文",
        },
        "basic": {
            "type": "object",
            "description": "Lightroom 基本面板参数,范围与 LR 一致",
            "properties": {
                "temperature_shift": {"type": "number", "minimum": -100, "maximum": 100, "description": "色温偏移 -100(偏蓝) 到 100(偏黄),相对中性白平衡"},
                "tint_shift": {"type": "number", "minimum": -100, "maximum": 100, "description": "色调偏移 -100(偏绿) 到 100(偏品红)"},
                "exposure": {"type": "number", "minimum": -5.0, "maximum": 5.0, "description": "曝光 -5.0 到 +5.0 EV"},
                "contrast": {"type": "number", "minimum": -100, "maximum": 100, "description": "对比度 -100 到 100"},
                "highlights": {"type": "number", "minimum": -100, "maximum": 100, "description": "高光 -100 到 100"},
                "shadows": {"type": "number", "minimum": -100, "maximum": 100, "description": "阴影 -100 到 100"},
                "whites": {"type": "number", "minimum": -100, "maximum": 100, "description": "白色色阶 -100 到 100"},
                "blacks": {"type": "number", "minimum": -100, "maximum": 100, "description": "黑色色阶 -100 到 100"},
                "texture": {"type": "number", "minimum": -100, "maximum": 100, "description": "纹理 -100 到 100"},
                "clarity": {"type": "number", "minimum": -100, "maximum": 100, "description": "清晰度 -100 到 100"},
                "dehaze": {"type": "number", "minimum": -100, "maximum": 100, "description": "去朦胧 -100 到 100"},
                "vibrance": {"type": "number", "minimum": -100, "maximum": 100, "description": "自然饱和度 -100 到 100"},
                "saturation": {"type": "number", "minimum": -100, "maximum": 100, "description": "饱和度 -100 到 100"},
            },
            "required": [
                "temperature_shift", "tint_shift", "exposure", "contrast",
                "highlights", "shadows", "whites", "blacks",
                "texture", "clarity", "dehaze", "vibrance", "saturation",
            ],
            "additionalProperties": False,
        },
        "tone_curve": {
            "type": "array",
            "description": "RGB 主曲线控制点(0-255 输入/输出),至少含 (0,0) 和 (255,255) 附近的端点;胶片感的褪色黑用抬高的暗部端点表示",
            "items": {
                "type": "object",
                "properties": {
                    "input": {"type": "number", "minimum": 0, "maximum": 255},
                    "output": {"type": "number", "minimum": 0, "maximum": 255},
                },
                "required": ["input", "output"],
                "additionalProperties": False,
            },
        },
        "hsl": {
            "type": "array",
            "description": "HSL 混色器,8 个颜色通道各一项",
            "items": {
                "type": "object",
                "properties": {
                    "color": {"type": "string", "enum": _COLOR_KEYS},
                    "hue": {"type": "number", "minimum": -100, "maximum": 100, "description": "色相 -100 到 100"},
                    "saturation": {"type": "number", "minimum": -100, "maximum": 100, "description": "饱和度 -100 到 100"},
                    "luminance": {"type": "number", "minimum": -100, "maximum": 100, "description": "明亮度 -100 到 100"},
                },
                "required": ["color", "hue", "saturation", "luminance"],
                "additionalProperties": False,
            },
        },
        "color_grading": {
            "type": "object",
            "description": "颜色分级(色轮):阴影/中间调/高光/全局",
            "properties": {
                "shadows": _HUE_SAT_LUM,
                "midtones": _HUE_SAT_LUM,
                "highlights": _HUE_SAT_LUM,
                "global_": _HUE_SAT_LUM,
                "blending": {"type": "number", "minimum": 0, "maximum": 100, "description": "混合 0-100,默认 50"},
                "balance": {"type": "number", "minimum": -100, "maximum": 100, "description": "平衡 -100 到 100"},
            },
            "required": ["shadows", "midtones", "highlights", "global_", "blending", "balance"],
            "additionalProperties": False,
        },
        "effects": {
            "type": "object",
            "properties": {
                "vignette_amount": {"type": "number", "minimum": -100, "maximum": 100, "description": "暗角 -100 到 100,0 为无"},
                "grain_amount": {"type": "number", "minimum": 0, "maximum": 100, "description": "颗粒 0 到 100"},
            },
            "required": ["vignette_amount", "grain_amount"],
            "additionalProperties": False,
        },
    },
    "required": ["summary", "steps", "basic", "tone_curve", "hsl", "color_grading", "effects"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """你是一位资深的摄影后期调色师,精通 Adobe Lightroom 和 Camera Raw 的全部参数体系,\
熟悉各种经典胶片模拟、电影调色和知名摄影师的风格。

你的任务是分析照片的色调与影调,逆向推断出在 Lightroom 中复现这种风格所需的参数。

分析时按以下顺序观察:
1. 影调结构:直方图分布、黑场是否褪色(matte black)、高光是否压暗、整体反差
2. 白平衡倾向:整体偏暖/偏冷、偏绿/偏品
3. 分离色调:阴影和高光分别被染了什么颜色(这是大多数"电影感/胶片感"的核心)
4. 各颜色通道:肤色橙色的处理、天空蓝色的偏移、绿色植物是否偏黄/降饱和
5. 质感:清晰度、纹理、颗粒、暗角

如果同时给了原片和成片,请精确对比两者差异来推断参数,而不是凭感觉。\
只给成片时,以中性、标准还原的假想原片为基准估计。

参数要保守务实:普通照片的调整大多在 ±40 以内,不要给出极端值,除非风格确实极端。\
没有被调整的项就给 0(色轮的 hue 给 0、saturation 给 0)。"""


# ---------------------------------------------------------------- 后端选择

def resolve_backend(backend: str = "auto") -> str:
    """兼容入口:返回 auto 解析后的后端名(测试与 cli 打印用)。"""
    p = providers.get_provider(backend)
    return "api" if isinstance(p, providers.AnthropicProvider) else "cli"


MAX_IMAGES = 5

_MULTI_TASK = """这些成片来自同一种风格(同一位摄影师/同一套预设)。
请归纳它们**共同**的风格特征——忽略单张的题材、光线差异,关注反复出现的
色调倾向、影调结构、染色方式;参数给出能同时逼近各张的折中值。"""


def analyze(
    edited: str | Path | list[str | Path],
    original: str | Path | None = None,
    style_hint: str | None = None,
    backend: str = "auto",
) -> dict[str, Any]:
    """分析一张或多张成片(单张时可选对照原片),返回符合 ANALYSIS_SCHEMA 的参数字典。"""
    images = [edited] if isinstance(edited, (str, Path)) else list(edited)
    if len(images) > MAX_IMAGES:
        raise ValueError(f"一次最多分析 {MAX_IMAGES} 张成片(收到 {len(images)} 张)。")
    if len(images) > 1 and original is not None:
        raise ValueError("多张成片模式下不支持 --original 原片对照。")

    blocks: list[dict] = []
    if original is not None:
        blocks += [
            {"type": "image", "path": Path(original), "label": "修图前的原片"},
            {"type": "image", "path": Path(images[0]), "label": "后期完成的成片"},
            {"type": "text", "text": "请精确对比原片和成片,推断出从原片调到成片所用的 Lightroom 参数。"},
        ]
    elif len(images) == 1:
        blocks += [
            {"type": "image", "path": Path(images[0]), "label": "后期完成的照片"},
            {"type": "text", "text": "请分析这张后期完成的照片,推断出复现这种色调风格所需的 Lightroom 参数。"},
        ]
    else:
        blocks += [
            {"type": "image", "path": Path(p), "label": f"成片 {i}"} for i, p in enumerate(images, 1)
        ]
        blocks.append({"type": "text", "text": _MULTI_TASK})
    if style_hint:
        blocks.append({"type": "text", "text": f"补充信息:{style_hint}"})

    result = providers.get_provider(backend).complete(SYSTEM_PROMPT, blocks, ANALYSIS_SCHEMA)
    return _normalize(result)


def _normalize(analysis: dict[str, Any]) -> dict[str, Any]:
    """补全缺失字段。CLI 后端没有结构化输出的硬约束,模型偶尔会漏字段。"""
    analysis.setdefault("summary", "")
    analysis.setdefault("steps", [])
    analysis.setdefault("tone_curve", [])
    analysis.setdefault("hsl", [])
    analysis.setdefault("effects", {})
    analysis["effects"].setdefault("vignette_amount", 0)
    analysis["effects"].setdefault("grain_amount", 0)

    basic = analysis.setdefault("basic", {})
    for key in ANALYSIS_SCHEMA["properties"]["basic"]["required"]:
        basic.setdefault(key, 0)

    cg = analysis.setdefault("color_grading", {})
    for zone in ("shadows", "midtones", "highlights", "global_"):
        z = cg.setdefault(zone, {})
        for k in ("hue", "saturation", "luminance"):
            z.setdefault(k, 0)
    cg.setdefault("blending", 50)
    cg.setdefault("balance", 0)

    for entry in analysis["hsl"]:
        for k in ("hue", "saturation", "luminance"):
            entry.setdefault(k, 0)
    analysis["tone_curve"] = [
        p for p in analysis["tone_curve"]
        if isinstance(p, dict) and "input" in p and "output" in p
    ]
    return analysis


# ---------------------------------------------------------------- 迭代校准

_REFINE_TASK = """这是一次迭代校准:用户之前用下面的参数模版处理了照片,但和目标成片还有差距。
请对比「当前效果图」和「目标成片」的差异,在现有参数基础上修正,输出修正后的**完整**参数
(不是增量,是修正后的最终值;没问题的参数保持原值)。
在 summary 里说明这次修正了什么、为什么;steps 里只列出相对上一版的改动点。"""


def refine(
    current_params: dict[str, Any],
    attempt: str | Path,
    target: str | Path,
    backend: str = "auto",
) -> dict[str, Any]:
    """对比套用当前参数后的效果图与目标成片,返回修正后的完整参数。"""
    blocks = [
        {"type": "text", "text": _REFINE_TASK},
        {"type": "text", "text": f"当前参数模版:\n{json.dumps(current_params, ensure_ascii=False)}"},
        {"type": "image", "path": Path(attempt), "label": "套用当前参数后导出的效果图"},
        {"type": "image", "path": Path(target), "label": "想要达到的目标成片"},
    ]
    result = providers.get_provider(backend).complete(SYSTEM_PROMPT, blocks, ANALYSIS_SCHEMA)
    return _normalize(result)
