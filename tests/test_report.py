"""report.py 单元测试：HSL 颜色回退分支的转义（code review follow-up，Critical/XSS）。

`_HSL_CN.get(color, color)` 在 `color` 不是 8 个已知颜色之一时会原样回退成
`color` 本身；这个回退分支此前没有 `escape`，一个未知/恶意的 `color` 字符串
会被直接拼进 HTML。`GET /report/<name>` 现在是 GUI-T10 落地后的活路由，
`POST /api/looks` 又给 analysis 加了结构校验（见 test_gui_looks_api.py 的
`test_post_looks_rejects_hsl_color_outside_enum`），两层修复分别在
`report.py`（本文件测的这一层：即便有人绕开 API 直接调
`render_report`——比如 CLI 的 `report <template>`，读到一份被手改过的
风格库 json——也不会被 XSS）和 `api.py`（`test_gui_looks_api.py` 测的
另一层：从源头挡掉不合法的 color）。
"""
from __future__ import annotations

from looklift import report


def test_render_report_escapes_unknown_hsl_color_fallback(sample_analysis):
    analysis = dict(sample_analysis)
    analysis["hsl"] = [{"color": "unknowncolor<b>", "hue": 1, "saturation": 1, "luminance": 1}]

    html = report.render_report(analysis, "test")

    assert "<b>" not in html
    assert "unknowncolor&lt;b&gt;" in html


def test_render_report_known_color_still_renders_chinese_label(sample_analysis):
    """回归：修复转义不能连带把正常的中文颜色名标签搞坏。"""
    analysis = dict(sample_analysis)
    analysis["hsl"] = [{"color": "blue", "hue": -15, "saturation": 12, "luminance": -10}]

    html = report.render_report(analysis, "test")

    assert "蓝" in html
