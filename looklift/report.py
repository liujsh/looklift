"""把分析模版渲染成自包含的 HTML 风格报告(零外部依赖,可直接分享)。"""

from __future__ import annotations

from html import escape
from typing import Any

_BASIC_LABELS = [
    ("temperature_shift", "色温"), ("tint_shift", "色调"), ("exposure", "曝光"),
    ("contrast", "对比度"), ("highlights", "高光"), ("shadows", "阴影"),
    ("whites", "白色"), ("blacks", "黑色"), ("texture", "纹理"),
    ("clarity", "清晰度"), ("dehaze", "去朦胧"), ("vibrance", "自然饱和度"),
    ("saturation", "饱和度"),
]

# HSL 面板 8 个通道的代表色(用于表格色块)
_HSL_SWATCH = {
    "red": "#e53935", "orange": "#fb8c00", "yellow": "#fdd835", "green": "#43a047",
    "aqua": "#00acc1", "blue": "#1e88e5", "purple": "#8e24aa", "magenta": "#d81b60",
}
_HSL_CN = {
    "red": "红", "orange": "橙", "yellow": "黄", "green": "绿",
    "aqua": "浅绿", "blue": "蓝", "purple": "紫", "magenta": "品红",
}

_CSS = """
body { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; max-width: 860px;
       margin: 2rem auto; padding: 0 1rem; color: #222; background: #fafafa; line-height: 1.7; }
h1 { border-bottom: 3px solid #333; padding-bottom: .4rem; }
h2 { margin-top: 2.2rem; color: #444; }
table { border-collapse: collapse; width: 100%; background: #fff; }
th, td { border: 1px solid #ddd; padding: .45rem .8rem; text-align: left; }
th { background: #f0f0f0; font-weight: 600; }
.pos { color: #c62828; font-weight: 600; }
.neg { color: #1565c0; font-weight: 600; }
.zero { color: #aaa; }
.swatch { display: inline-block; width: 14px; height: 14px; border-radius: 3px;
          margin-right: 6px; vertical-align: -2px; border: 1px solid rgba(0,0,0,.15); }
.summary { background: #fff; border-left: 4px solid #555; padding: .8rem 1.2rem; }
ol li { margin: .35rem 0; }
.curve-box { background: #fff; border: 1px solid #ddd; display: inline-block; padding: 12px; }
footer { margin-top: 3rem; color: #999; font-size: .85rem; }
"""


def _fmt(v: float, decimals: int = 0) -> str:
    if not v:
        return '<span class="zero">0</span>'
    cls = "pos" if v > 0 else "neg"
    text = f"{v:+.{decimals}f}" if decimals else f"{v:+g}"
    return f'<span class="{cls}">{text}</span>'


def _curve_svg(points: list[dict[str, Any]], size: int = 256) -> str:
    """曲线图:灰色对角参考线 + 平滑曲线(Catmull-Rom 转贝塞尔)+ 控制点。"""
    pts = sorted(
        ((float(p["input"]), float(p["output"])) for p in points),
        key=lambda t: t[0],
    )
    if len(pts) < 2:
        pts = [(0.0, 0.0), (255.0, 255.0)]

    def xy(p: tuple[float, float]) -> tuple[float, float]:
        return p[0] / 255 * size, size - p[1] / 255 * size

    # Catmull-Rom → cubic bezier
    ext = [pts[0]] + pts + [pts[-1]]
    d = f"M {xy(pts[0])[0]:.1f} {xy(pts[0])[1]:.1f}"
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = (xy(ext[j]) for j in (i - 1, i, i + 1, i + 2))
        c1 = (p1[0] + (p2[0] - p0[0]) / 6, p1[1] + (p2[1] - p0[1]) / 6)
        c2 = (p2[0] - (p3[0] - p1[0]) / 6, p2[1] - (p3[1] - p1[1]) / 6)
        d += f" C {c1[0]:.1f} {c1[1]:.1f}, {c2[0]:.1f} {c2[1]:.1f}, {p2[0]:.1f} {p2[1]:.1f}"

    dots = "".join(
        f'<circle cx="{xy(p)[0]:.1f}" cy="{xy(p)[1]:.1f}" r="4" fill="#333"/>' for p in pts
    )
    grid = "".join(
        f'<line x1="{size * k / 4:.0f}" y1="0" x2="{size * k / 4:.0f}" y2="{size}" stroke="#eee"/>'
        f'<line x1="0" y1="{size * k / 4:.0f}" x2="{size}" y2="{size * k / 4:.0f}" stroke="#eee"/>'
        for k in range(1, 4)
    )
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}">'
        f'<rect width="{size}" height="{size}" fill="#fff" stroke="#ccc"/>'
        f"{grid}"
        f'<line x1="0" y1="{size}" x2="{size}" y2="0" stroke="#ccc" stroke-dasharray="4 4"/>'
        f'<path d="{d}" fill="none" stroke="#333" stroke-width="2.5"/>'
        f"{dots}</svg>"
    )


def _grading_row(cn: str, zone: dict[str, Any]) -> str:
    hue, sat, lum = zone.get("hue", 0), zone.get("saturation", 0), zone.get("luminance", 0)
    if sat:
        swatch = f'<span class="swatch" style="background:hsl({hue:g},{max(sat, 25):g}%,55%)"></span>'
    else:
        swatch = '<span class="swatch" style="background:#eee"></span>'
    return (
        f"<tr><td>{swatch}{cn}</td><td>{hue:g}°</td>"
        f"<td>{_fmt(sat) if sat else '<span class=zero>0</span>'}</td><td>{_fmt(lum)}</td></tr>"
    )


def render_report(analysis: dict[str, Any], name: str) -> str:
    b = analysis.get("basic", {})
    basic_rows = "".join(
        f"<tr><td>{cn}</td><td>{_fmt(b.get(key, 0), 2 if key == 'exposure' else 0)}</td></tr>"
        for key, cn in _BASIC_LABELS
    )

    steps = "".join(f"<li>{escape(s)}</li>" for s in analysis.get("steps", []))

    hsl_rows = ""
    for entry in analysis.get("hsl", []):
        color = entry.get("color", "")
        swatch = f'<span class="swatch" style="background:{_HSL_SWATCH.get(color, "#999")}"></span>'
        hsl_rows += (
            # review fix(Critical/XSS):找不到映射时原样回退成 color 本身——
            # color 是 analysis 里的用户/AI 可控字段,不经 escape 直接拼进
            # HTML 会被浏览器当成标签执行(GET /report/<name> 现在是活路由,
            # 上游 POST /api/looks 只做了 isinstance(dict) 校验，两者叠加
            # 就是一条未转义 XSS 路径)。summary/steps/name 已经 escape 过，
            # 这里补上；本文件其余把 analysis 数值拼进 HTML 的地方
            # （_grading_row 的 hue/sat/lum、tone_curve、effects）都先经过
            # `:g`/`float()` 数值格式化，非数字输入会直接抛异常而不是被当
            # HTML 执行，不是同一类风险，已核对过不需要同样处理。
            f"<tr><td>{swatch}{escape(_HSL_CN.get(color, color))}</td>"
            f"<td>{_fmt(entry.get('hue', 0))}</td>"
            f"<td>{_fmt(entry.get('saturation', 0))}</td>"
            f"<td>{_fmt(entry.get('luminance', 0))}</td></tr>"
        )

    cg = analysis.get("color_grading", {})
    grading_rows = "".join(
        _grading_row(cn, cg.get(zone, {}))
        for zone, cn in [("shadows", "阴影"), ("midtones", "中间调"),
                         ("highlights", "高光"), ("global_", "全局")]
    )

    fx = analysis.get("effects", {})

    return f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>{escape(name)} — looklift 风格报告</title>
<style>{_CSS}</style>
</head>
<body>
<h1>🎨 {escape(name)}</h1>

<h2>风格分析</h2>
<div class="summary">{escape(analysis.get("summary", ""))}</div>

<h2>后期步骤</h2>
<ol>{steps}</ol>

<h2>基本面板</h2>
<table><tr><th>参数</th><th>值</th></tr>{basic_rows}</table>

<h2>色调曲线</h2>
<div class="curve-box">{_curve_svg(analysis.get("tone_curve", []))}</div>

<h2>HSL 混色器</h2>
<table><tr><th>通道</th><th>色相</th><th>饱和度</th><th>明亮度</th></tr>{hsl_rows}</table>

<h2>颜色分级</h2>
<table><tr><th>区域</th><th>色相</th><th>饱和度</th><th>明亮度</th></tr>{grading_rows}</table>
<p>混合 {cg.get("blending", 50):g} · 平衡 {cg.get("balance", 0):+g}</p>

<h2>效果</h2>
<p>暗角 {fx.get("vignette_amount", 0):+g} · 颗粒 {fx.get("grain_amount", 0):g}</p>

<footer>由 <a href="https://github.com/liujsh/looklift">looklift</a> 生成</footer>
</body>
</html>
"""
