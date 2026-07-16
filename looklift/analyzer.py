"""从成片(可选:对照原片)逆向推断 Lightroom 调整参数。

两种后端:
- "cli": 调用本地 Claude Code CLI(`claude -p`),走 Claude Code 登录额度,无需 API key
- "api": 调用 Anthropic API(需要 ANTHROPIC_API_KEY),有结构化输出保证
- "auto": 有 ANTHROPIC_API_KEY 则用 api,否则用 cli
"""

from __future__ import annotations

import base64
import io
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

MODEL = "claude-opus-4-8"
MAX_EDGE = 1568  # 控制图片 token 消耗;分析色调影调无需原始分辨率

_COLOR_KEYS = ["red", "orange", "yellow", "green", "aqua", "blue", "purple", "magenta"]

_HUE_SAT_LUM = {
    "type": "object",
    "properties": {
        "hue": {"type": "number", "description": "色相角度 0-360,0 表示未着色"},
        "saturation": {"type": "number", "description": "饱和度 0 到 100"},
        "luminance": {"type": "number", "description": "明亮度 -100 到 100"},
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
                "temperature_shift": {"type": "number", "description": "色温偏移 -100(偏蓝) 到 100(偏黄),相对中性白平衡"},
                "tint_shift": {"type": "number", "description": "色调偏移 -100(偏绿) 到 100(偏品红)"},
                "exposure": {"type": "number", "description": "曝光 -5.0 到 +5.0 EV"},
                "contrast": {"type": "number", "description": "对比度 -100 到 100"},
                "highlights": {"type": "number", "description": "高光 -100 到 100"},
                "shadows": {"type": "number", "description": "阴影 -100 到 100"},
                "whites": {"type": "number", "description": "白色色阶 -100 到 100"},
                "blacks": {"type": "number", "description": "黑色色阶 -100 到 100"},
                "texture": {"type": "number", "description": "纹理 -100 到 100"},
                "clarity": {"type": "number", "description": "清晰度 -100 到 100"},
                "dehaze": {"type": "number", "description": "去朦胧 -100 到 100"},
                "vibrance": {"type": "number", "description": "自然饱和度 -100 到 100"},
                "saturation": {"type": "number", "description": "饱和度 -100 到 100"},
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
                    "input": {"type": "number"},
                    "output": {"type": "number"},
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
                    "hue": {"type": "number", "description": "色相 -100 到 100"},
                    "saturation": {"type": "number", "description": "饱和度 -100 到 100"},
                    "luminance": {"type": "number", "description": "明亮度 -100 到 100"},
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
                "blending": {"type": "number", "description": "混合 0-100,默认 50"},
                "balance": {"type": "number", "description": "平衡 -100 到 100"},
            },
            "required": ["shadows", "midtones", "highlights", "global_", "blending", "balance"],
            "additionalProperties": False,
        },
        "effects": {
            "type": "object",
            "properties": {
                "vignette_amount": {"type": "number", "description": "暗角 -100 到 100,0 为无"},
                "grain_amount": {"type": "number", "description": "颗粒 0 到 100"},
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
    if backend == "auto":
        if os.environ.get("ANTHROPIC_API_KEY"):
            return "api"
        if shutil.which("claude"):
            return "cli"
        raise RuntimeError(
            "未找到可用后端:请设置 ANTHROPIC_API_KEY,或安装 Claude Code CLI(claude 命令)。"
        )
    return backend


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

    backend = resolve_backend(backend)
    if backend == "cli":
        result = _analyze_via_cli(images, original, style_hint)
    else:
        result = _analyze_via_api(images, original, style_hint)
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


# ---------------------------------------------------------------- CLI 后端

def _analyze_via_cli(
    images: list[str | Path],
    original: str | Path | None,
    style_hint: str | None,
) -> dict[str, Any]:
    """通过本地 Claude Code CLI 分析,走 Claude Code 登录额度。"""
    claude = shutil.which("claude")
    if not claude:
        raise RuntimeError("未找到 claude 命令,请先安装 Claude Code CLI。")

    parts = [SYSTEM_PROMPT, ""]
    if original is not None:
        parts.append(f"请先用 Read 工具查看原片: {Path(original).resolve()}")
        parts.append(f"再用 Read 工具查看成片: {Path(images[0]).resolve()}")
        parts.append("然后精确对比两者,推断出从原片调到成片所用的 Lightroom 参数。")
    elif len(images) == 1:
        parts.append(f"请用 Read 工具查看这张后期完成的照片: {Path(images[0]).resolve()}")
        parts.append("然后推断出复现这种色调风格所需的 Lightroom 参数。")
    else:
        parts.append(f"请用 Read 工具依次查看这 {len(images)} 张后期完成的成片:")
        parts.extend(f"  {i + 1}. {Path(p).resolve()}" for i, p in enumerate(images))
        parts.append(_MULTI_TASK)
    if style_hint:
        parts.append(f"补充信息:{style_hint}")
    return _run_cli(claude, parts)


def _run_cli(claude: str, parts: list[str]) -> dict[str, Any]:
    """拼上 schema 要求后调用 claude CLI,返回解析出的 JSON。"""
    parts = parts + [
        "最终回答必须且只能是一个 JSON 对象(不要 markdown 代码块),严格符合以下 JSON Schema:\n"
        + json.dumps(ANALYSIS_SCHEMA, ensure_ascii=False)
    ]
    prompt = "\n".join(parts)

    # prompt 从 stdin 传入:Windows 上 claude 是 .CMD 包装,命令行参数有 ~8K 长度上限,
    # 带完整 JSON Schema 的 prompt 会被截断
    proc = subprocess.run(
        [claude, "-p", "--output-format", "json", "--allowedTools", "Read"],
        input=prompt,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=600,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude CLI 调用失败:\n{proc.stderr or proc.stdout}")

    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(
            f"claude CLI 返回了非 JSON 输出:\nstdout: {proc.stdout[:500]}\nstderr: {proc.stderr[:500]}"
        ) from None
    result_text = envelope.get("result", "")
    return _extract_json(result_text)


def _extract_json(text: str) -> dict[str, Any]:
    """从文本中提取第一个完整的 JSON 对象。"""
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"未能从模型输出中解析出 JSON:\n{text[:500]}")
    return json.loads(text[start : end + 1])


# ---------------------------------------------------------------- API 后端

def _encode_image(path: str | Path) -> tuple[str, str]:
    """读取图片,必要时缩小,返回 (base64, media_type)。"""
    from PIL import Image

    img = Image.open(path)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    if max(img.size) > MAX_EDGE:
        img.thumbnail((MAX_EDGE, MAX_EDGE), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return base64.standard_b64encode(buf.getvalue()).decode(), "image/jpeg"


def _image_block(path: str | Path) -> dict[str, Any]:
    data, media_type = _encode_image(path)
    return {
        "type": "image",
        "source": {"type": "base64", "media_type": media_type, "data": data},
    }


def _analyze_via_api(
    images: list[str | Path],
    original: str | Path | None,
    style_hint: str | None,
) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if original is not None:
        content.append({"type": "text", "text": "这是修图前的原片:"})
        content.append(_image_block(original))
        content.append({"type": "text", "text": "这是后期完成的成片:"})
        content.append(_image_block(images[0]))
        prompt = "请精确对比原片和成片,推断出从原片调到成片所用的 Lightroom 参数。"
    elif len(images) == 1:
        content.append(_image_block(images[0]))
        prompt = "请分析这张后期完成的照片,推断出复现这种色调风格所需的 Lightroom 参数。"
    else:
        for i, p in enumerate(images, 1):
            content.append({"type": "text", "text": f"成片 {i}:"})
            content.append(_image_block(p))
        prompt = _MULTI_TASK

    if style_hint:
        prompt += f"\n补充信息:{style_hint}"
    content.append({"type": "text", "text": prompt})
    return _run_api(content)


def _run_api(content: list[dict[str, Any]]) -> dict[str, Any]:
    import anthropic

    client = anthropic.Anthropic()
    with client.messages.stream(
        model=MODEL,
        max_tokens=16000,
        system=SYSTEM_PROMPT,
        output_config={"format": {"type": "json_schema", "schema": ANALYSIS_SCHEMA}},
        messages=[{"role": "user", "content": content}],
    ) as stream:
        response = stream.get_final_message()

    if response.stop_reason == "refusal":
        raise RuntimeError("模型拒绝了本次请求,请换一张照片重试。")

    text = next(b.text for b in response.content if b.type == "text")
    return json.loads(text)


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
    backend = resolve_backend(backend)
    params_json = json.dumps(current_params, ensure_ascii=False)

    if backend == "cli":
        claude = shutil.which("claude")
        if not claude:
            raise RuntimeError("未找到 claude 命令,请先安装 Claude Code CLI。")
        parts = [
            SYSTEM_PROMPT,
            "",
            _REFINE_TASK,
            f"当前参数模版:\n{params_json}",
            f"请用 Read 工具查看套用当前参数后导出的效果图: {Path(attempt).resolve()}",
            f"再用 Read 工具查看想要达到的目标成片: {Path(target).resolve()}",
        ]
        result = _run_cli(claude, parts)
    else:
        content: list[dict[str, Any]] = [
            {"type": "text", "text": _REFINE_TASK},
            {"type": "text", "text": f"当前参数模版:\n{params_json}"},
            {"type": "text", "text": "这是套用当前参数后导出的效果图:"},
            _image_block(attempt),
            {"type": "text", "text": "这是想要达到的目标成片:"},
            _image_block(target),
        ]
        result = _run_api(content)

    return _normalize(result)
