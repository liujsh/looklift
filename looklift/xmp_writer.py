"""把分析结果转换成 Lightroom 可导入的 .xmp 预设文件 / RAW sidecar 文件。

Lightroom 预设本质是一个 XML 文本,调整参数以 crs:* 属性挂在 rdf:Description 上。
- 预设(.xmp):导入 Lightroom 后一键套用,含 crs:PresetType/crs:Name
- sidecar(与 RAW 同名的 .xmp):放在 RAW 文件旁边,LR/Camera Raw 打开 RAW 时自动读取
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape, quoteattr

_HSL_COLOR_MAP = {
    "red": "Red", "orange": "Orange", "yellow": "Yellow", "green": "Green",
    "aqua": "Aqua", "blue": "Blue", "purple": "Purple", "magenta": "Magenta",
}


def _signed(v: float, decimals: int = 0) -> str:
    """LR 对带符号参数的写法:正值带 + 前缀。"""
    if decimals:
        s = f"{v:+.{decimals}f}"
    else:
        s = f"{v:+.0f}"
    return "0" if float(v) == 0 else s


def _num(v: float) -> str:
    return f"{v:.0f}"


def analysis_to_crs(analysis: dict[str, Any]) -> dict[str, Any]:
    """把 analyzer 的结构化结果映射成 crs 参数字典(值为字符串或曲线点列表)。"""
    crs: dict[str, Any] = {}
    b = analysis.get("basic", {})

    crs["IncrementalTemperature"] = _signed(b.get("temperature_shift", 0))
    crs["IncrementalTint"] = _signed(b.get("tint_shift", 0))
    crs["Exposure2012"] = _signed(b.get("exposure", 0), decimals=2)
    crs["Contrast2012"] = _signed(b.get("contrast", 0))
    crs["Highlights2012"] = _signed(b.get("highlights", 0))
    crs["Shadows2012"] = _signed(b.get("shadows", 0))
    crs["Whites2012"] = _signed(b.get("whites", 0))
    crs["Blacks2012"] = _signed(b.get("blacks", 0))
    crs["Texture"] = _signed(b.get("texture", 0))
    crs["Clarity2012"] = _signed(b.get("clarity", 0))
    crs["Dehaze"] = _signed(b.get("dehaze", 0))
    crs["Vibrance"] = _signed(b.get("vibrance", 0))
    crs["Saturation"] = _signed(b.get("saturation", 0))

    # HSL 混色器
    for entry in analysis.get("hsl", []):
        color = _HSL_COLOR_MAP.get(entry.get("color", ""))
        if not color:
            continue
        crs[f"HueAdjustment{color}"] = _signed(entry.get("hue", 0))
        crs[f"SaturationAdjustment{color}"] = _signed(entry.get("saturation", 0))
        crs[f"LuminanceAdjustment{color}"] = _signed(entry.get("luminance", 0))

    # 颜色分级:阴影/高光沿用 SplitToning 字段名,中间调/全局用 ColorGrade 字段
    cg = analysis.get("color_grading", {})
    sh, mid, hi = cg.get("shadows", {}), cg.get("midtones", {}), cg.get("highlights", {})
    gl = cg.get("global_", {})
    crs["SplitToningShadowHue"] = _num(sh.get("hue", 0))
    crs["SplitToningShadowSaturation"] = _num(sh.get("saturation", 0))
    crs["SplitToningHighlightHue"] = _num(hi.get("hue", 0))
    crs["SplitToningHighlightSaturation"] = _num(hi.get("saturation", 0))
    crs["SplitToningBalance"] = _signed(cg.get("balance", 0))
    crs["ColorGradeMidtoneHue"] = _num(mid.get("hue", 0))
    crs["ColorGradeMidtoneSat"] = _num(mid.get("saturation", 0))
    crs["ColorGradeMidtoneLum"] = _signed(mid.get("luminance", 0))
    crs["ColorGradeShadowLum"] = _signed(sh.get("luminance", 0))
    crs["ColorGradeHighlightLum"] = _signed(hi.get("luminance", 0))
    crs["ColorGradeGlobalHue"] = _num(gl.get("hue", 0))
    crs["ColorGradeGlobalSat"] = _num(gl.get("saturation", 0))
    crs["ColorGradeGlobalLum"] = _signed(gl.get("luminance", 0))
    crs["ColorGradeBlending"] = _num(cg.get("blending", 50))

    # 曲线
    points = analysis.get("tone_curve", [])
    if points:
        crs["ToneCurveName2012"] = "Custom"
        crs["ToneCurvePV2012"] = [
            f"{round(p['input'])}, {round(p['output'])}" for p in points
        ]

    # 效果
    fx = analysis.get("effects", {})
    vignette = fx.get("vignette_amount", 0)
    if vignette:
        crs["PostCropVignetteAmount"] = _signed(vignette)
        crs["PostCropVignetteStyle"] = "1"
    grain = fx.get("grain_amount", 0)
    if grain:
        crs["GrainAmount"] = _num(grain)

    return crs


_CURVE_KEYS = {
    "ToneCurvePV2012", "ToneCurvePV2012Red", "ToneCurvePV2012Green", "ToneCurvePV2012Blue",
}


def _render_xmp(
    crs: dict[str, Any],
    preset_name: str | None = None,
) -> str:
    """渲染 XMP 文本。preset_name 非空时输出预设格式,否则输出 sidecar 格式。"""
    attrs: list[str] = [
        'crs:Version="15.4"',
        'crs:ProcessVersion="15.4"',
    ]
    if preset_name:
        attrs += [
            'crs:PresetType="Normal"',
            'crs:Cluster=""',
            f'crs:UUID="{uuid.uuid4().hex.upper()}"',
            'crs:SupportsAmount="False"',
            'crs:SupportsColor="True"',
            'crs:SupportsMonochrome="True"',
            'crs:SupportsHighDynamicRange="True"',
            'crs:SupportsNormalDynamicRange="True"',
            'crs:SupportsSceneReferred="True"',
            'crs:SupportsOutputReferred="True"',
        ]
    attrs.append('crs:WhiteBalance="As Shot"')

    elements: list[str] = []
    for key, value in crs.items():
        if key in _CURVE_KEYS and isinstance(value, list):
            lis = "\n     ".join(f"<rdf:li>{escape(v)}</rdf:li>" for v in value)
            elements.append(
                f"   <crs:{key}>\n    <rdf:Seq>\n     {lis}\n    </rdf:Seq>\n   </crs:{key}>"
            )
        else:
            attrs.append(f"crs:{key}={quoteattr(str(value))}")
    attrs.append('crs:HasSettings="True"')

    if preset_name:
        elements.insert(0, (
            "   <crs:Name>\n    <rdf:Alt>\n"
            f'     <rdf:li xml:lang="x-default">{escape(preset_name)}</rdf:li>\n'
            "    </rdf:Alt>\n   </crs:Name>"
        ))

    attr_block = "\n    ".join(attrs)
    elem_block = ("\n" + "\n".join(elements)) if elements else ""
    return f"""<x:xmpmeta xmlns:x="adobe:ns:meta/" x:xmptk="looklift 0.1">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    {attr_block}>{elem_block}
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>
"""


def write_preset(crs: dict[str, Any], name: str, out_path: str | Path) -> Path:
    """写出 Lightroom 预设 .xmp,导入方式:LR 预设面板 → 导入预设。"""
    out = Path(out_path)
    out.write_text(_render_xmp(crs, preset_name=name), encoding="utf-8")
    return out


def write_sidecar(crs: dict[str, Any], raw_path: str | Path) -> Path:
    """在 RAW 文件旁写出同名 .xmp sidecar,LR/Camera Raw 打开 RAW 时自动应用。"""
    raw = Path(raw_path)
    out = raw.with_suffix(".xmp")
    out.write_text(_render_xmp(crs, preset_name=None), encoding="utf-8")
    return out
