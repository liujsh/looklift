"""GUI-T10：风格库收藏/导出 + 报告页后端 —— `/api/looks*` 五条路由 + `/report/<name>`。

覆盖 tasks.md T13/T14 + design.md API 路由一览 + requirements.md U4/U8：
- `POST /api/looks`：落盘 json（缩放后 analysis）+ xmp 预设；factor 默认
  1.0；重名 409；非法名 400。
- `GET /api/looks`：列表，损坏 json 跳过，`has_preset` 标记正确。
- `GET /api/looks/<name>`：详情 200/404。
- `POST /api/looks/<name>/export`：无 sidecar 重新生成库内预设、有 sidecar
  写到 RAW 旁边；factor 缩放与"先 scale_analysis 再过 xmp_writer"的 CLI
  等价路径产出一致的 crs 参数（复用 test_xmp_writer.py 的断言思路：经
  `xmp_reader` 读回比较字段值，不比较含随机 UUID 的原始字节）。
- `GET /report/<name>`：与 `report.render_report` 同输入等价的 HTML；404。
- 静态结构：looks.js 存在且被 index.html 引入，且含 `window.open` 打开报告。

走真实 running server（复用 test_gui_preview_api.py / test_gui_analyze_api.py
的 fixture 写法）。用 `monkeypatch.chdir(tmp_path)` + 预先建好 `looks/` 目录
隔离 `config.looks_dir()`——cwd 若含真实的 `looks/` 目录会被优先选中（见
`config.looks_dir` 的 cwd 优先规则），仓库根目录本身就有一份真实风格库，
测试必须先把 cwd 换到临时目录，不然会读写到它。
"""
from __future__ import annotations

import http.client
import json
import threading
from pathlib import Path

import pytest

from looklift import config, intensity, report, xmp_reader, xmp_writer
from looklift.gui import server as gui_server


@pytest.fixture
def running_server(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "looks").mkdir()
    srv = gui_server.create_server(port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def _request(srv, method: str, path: str, payload: dict | None = None):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
    try:
        body = json.dumps(payload).encode("utf-8") if payload is not None else b""
        headers = {"Content-Type": "application/json"}
        conn.request(method, path, body=body, headers=headers)
        resp = conn.getresponse()
        raw = resp.read()
        return resp.status, json.loads(raw)
    finally:
        conn.close()


def _request_raw(srv, method: str, path: str):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
    try:
        conn.request(method, path)
        resp = conn.getresponse()
        raw = resp.read()
        return resp.status, resp.getheader("Content-Type"), raw
    finally:
        conn.close()


# ─── POST /api/looks：收藏 ──────────────────────────────────────────────


def test_post_looks_saves_scaled_json_and_readable_xmp(running_server, tmp_path, sample_analysis):
    status, data = _request(
        running_server, "POST", "/api/looks",
        {"name": "胶片青橙", "analysis": sample_analysis, "factor": 0.7},
    )
    assert status == 200
    assert data["name"] == "胶片青橙"

    looks_dir = tmp_path / "looks"
    json_path = looks_dir / "胶片青橙.json"
    xmp_path = looks_dir / "胶片青橙.xmp"
    assert json_path.is_file()
    assert xmp_path.is_file()

    saved = json.loads(json_path.read_text(encoding="utf-8"))
    expected = intensity.scale_analysis(sample_analysis, 0.7)
    assert saved == expected

    settings = xmp_reader.read_crs_settings(xmp_path)
    assert settings is not None
    assert settings["PresetType"] == "Normal"
    expected_crs = xmp_writer.analysis_to_crs(expected)
    assert settings["Exposure2012"] == expected_crs["Exposure2012"]
    assert settings["HueAdjustmentBlue"] == expected_crs["HueAdjustmentBlue"]


def test_post_looks_default_factor_is_full_strength(running_server, tmp_path, sample_analysis):
    status, _ = _request(running_server, "POST", "/api/looks", {"name": "AAA", "analysis": sample_analysis})
    assert status == 200
    saved = json.loads((tmp_path / "looks" / "AAA.json").read_text(encoding="utf-8"))
    assert saved == intensity.scale_analysis(sample_analysis, 1.0)


def test_post_looks_duplicate_name_returns_409(running_server, sample_analysis):
    status1, _ = _request(running_server, "POST", "/api/looks", {"name": "dup", "analysis": sample_analysis})
    assert status1 == 200
    status2, data2 = _request(running_server, "POST", "/api/looks", {"name": "dup", "analysis": sample_analysis})
    assert status2 == 409
    assert "error" in data2


@pytest.mark.parametrize("bad_name", ["../x", "a/b", "a:b", "", " "])
def test_post_looks_invalid_name_returns_400(running_server, sample_analysis, bad_name):
    """`" "`（纯空白）是 code review follow-up 补的用例——`_validate_look_name`
    此前只用 `not name` 判空，纯空白字符串是"真值"，会漏过去。"""
    status, data = _request(
        running_server, "POST", "/api/looks", {"name": bad_name, "analysis": sample_analysis}
    )
    assert status == 400
    assert "error" in data


def test_post_looks_missing_analysis_returns_400(running_server):
    status, data = _request(running_server, "POST", "/api/looks", {"name": "no-analysis"})
    assert status == 400
    assert "error" in data


# ─── POST /api/looks：analysis 结构校验（code review Critical/XSS 修复）────
#
# `GET /report/<name>` 现在是活路由，`report.py` 的 `_HSL_CN.get(color,
# color)` 在 color 不是 8 个已知颜色之一时会原样回退（该文件已经补了
# escape，见 tests/test_report.py）；这里补的是源头这一层：不让任意字符串
# 混进 `hsl[].color` 这类"应该是受控枚举"的字段。


def test_post_looks_rejects_hsl_color_outside_enum(running_server, sample_analysis):
    """复现 reviewer 给的攻击载荷：`hsl[].color` 塞一段 `<script>`，收藏必须
    被结构校验拦在 400，而不是落盘等着 `/report/<name>` 把它吐回浏览器。"""
    malicious = json.loads(json.dumps(sample_analysis))
    malicious["hsl"] = [{"color": "<script>alert(1)</script>", "hue": 0, "saturation": 0, "luminance": 0}]

    status, data = _request(running_server, "POST", "/api/looks", {"name": "xss", "analysis": malicious})
    assert status == 400
    assert "error" in data


def test_post_looks_rejects_unknown_top_level_key(running_server, sample_analysis):
    malicious = dict(sample_analysis)
    malicious["__proto__"] = "whatever"
    status, data = _request(running_server, "POST", "/api/looks", {"name": "extra-key", "analysis": malicious})
    assert status == 400
    assert "error" in data


def test_post_looks_rejects_non_string_summary(running_server, sample_analysis):
    malicious = dict(sample_analysis)
    malicious["summary"] = {"not": "a string"}
    status, data = _request(running_server, "POST", "/api/looks", {"name": "bad-summary", "analysis": malicious})
    assert status == 400
    assert "error" in data


def test_post_looks_rejects_non_string_steps_items(running_server, sample_analysis):
    malicious = dict(sample_analysis)
    malicious["steps"] = [{"nested": "object"}]
    status, data = _request(running_server, "POST", "/api/looks", {"name": "bad-steps", "analysis": malicious})
    assert status == 400
    assert "error" in data


# ─── GET /api/looks：列表 ───────────────────────────────────────────────


def test_get_looks_lists_valid_entries_and_skips_corrupt(running_server, tmp_path, sample_analysis):
    looks_dir = tmp_path / "looks"
    (looks_dir / "good1.json").write_text(
        json.dumps(sample_analysis, ensure_ascii=False), encoding="utf-8"
    )
    (looks_dir / "good1.xmp").write_text("<x/>", encoding="utf-8")
    long_summary = "很长的风格概述" * 20
    (looks_dir / "good2.json").write_text(
        json.dumps({"summary": long_summary}, ensure_ascii=False), encoding="utf-8"
    )
    (looks_dir / "bad.json").write_text("{not valid json", encoding="utf-8")

    status, data = _request(running_server, "GET", "/api/looks")
    assert status == 200
    entries = data["looks"]
    names = {e["name"] for e in entries}
    assert names == {"good1", "good2"}

    good1 = next(e for e in entries if e["name"] == "good1")
    assert good1["has_preset"] is True
    assert good1["summary"] == sample_analysis["summary"]

    good2 = next(e for e in entries if e["name"] == "good2")
    assert good2["has_preset"] is False
    assert good2["summary"].endswith("…")
    assert len(good2["summary"]) == 81  # 80 字 + 省略号


def test_get_looks_empty_when_no_looks_dir_content(running_server):
    status, data = _request(running_server, "GET", "/api/looks")
    assert status == 200
    assert data["looks"] == []


# ─── GET /api/looks/<name>：详情 ────────────────────────────────────────


def test_get_look_detail_returns_stored_analysis(running_server, sample_analysis):
    _request(running_server, "POST", "/api/looks", {"name": "detail", "analysis": sample_analysis})
    status, data = _request(running_server, "GET", "/api/looks/detail")
    assert status == 200
    assert data == intensity.scale_analysis(sample_analysis, 1.0)


def test_get_look_detail_unknown_name_returns_404(running_server):
    status, data = _request(running_server, "GET", "/api/looks/nope")
    assert status == 404
    assert "error" in data


# ─── POST /api/looks/<name>/export ─────────────────────────────────────


def test_export_without_sidecar_regenerates_preset_at_absolute_path(
    running_server, tmp_path, sample_analysis
):
    _request(running_server, "POST", "/api/looks", {"name": "expo", "analysis": sample_analysis})
    status, data = _request(running_server, "POST", "/api/looks/expo/export", {})
    assert status == 200
    preset_path = Path(data["preset"])
    assert preset_path.is_absolute()
    assert preset_path.is_file()
    assert preset_path == (tmp_path / "looks" / "expo.xmp").resolve()


def test_export_factor_matches_scale_then_write_preset_pipeline(
    running_server, sample_analysis
):
    """导出的预设内容应与"先 scale_analysis 再过 xmp_writer"的（CLI apply 等
    价）路径产出的 crs 参数逐字段相等——不比较原始 XML 字节，因为
    `xmp_writer.write_preset` 每次都会生成一个新随机 UUID（`crs:UUID`），
    两次独立写出的文件字节必然不同，真正该验证的是参数值。
    """
    _request(running_server, "POST", "/api/looks", {"name": "cmp", "analysis": sample_analysis})
    status, data = _request(running_server, "POST", "/api/looks/cmp/export", {"factor": 0.6})
    assert status == 200

    settings = xmp_reader.read_crs_settings(Path(data["preset"]))
    expected_crs = xmp_writer.analysis_to_crs(intensity.scale_analysis(sample_analysis, 0.6))
    for key, value in expected_crs.items():
        assert settings[key] == value, f"{key} 不等价：{settings.get(key)!r} != {value!r}"


def test_export_factor_compounds_on_already_scaled_saved_analysis(running_server, sample_analysis):
    """code review follow-up（Important）：上一条测试保存时用的是默认 factor
    1.0（恒等缩放），没能钉住 `_export_look` docstring 里写的"factor 存在时
    在库里已经缩放过的 analysis 基础上再缩放一次"这句话——1.0 是恒等元，
    掩盖了"复合"和"从原始 analysis 直接缩放"这两种语义的差异。这里保存时
    用 factor=0.7，导出时再传 factor=0.6，断言导出结果等于
    `scale_analysis(scale_analysis(sample_analysis, 0.7), 0.6)`（复合缩放），
    而不是 `scale_analysis(sample_analysis, 0.6)`（如果实现错误地"忘记"
    收藏时已经缩放过一次，会得到后者）。
    """
    _request(
        running_server, "POST", "/api/looks",
        {"name": "compound", "analysis": sample_analysis, "factor": 0.7},
    )
    status, data = _request(running_server, "POST", "/api/looks/compound/export", {"factor": 0.6})
    assert status == 200

    settings = xmp_reader.read_crs_settings(Path(data["preset"]))
    compound_crs = xmp_writer.analysis_to_crs(
        intensity.scale_analysis(intensity.scale_analysis(sample_analysis, 0.7), 0.6)
    )
    naive_crs = xmp_writer.analysis_to_crs(intensity.scale_analysis(sample_analysis, 0.6))

    for key, value in compound_crs.items():
        assert settings[key] == value, f"{key} 应等于复合缩放结果：{settings.get(key)!r} != {value!r}"

    # 健全性检查：确认复合缩放与"忘记已缩放过一次"的朴素结果确实不同，
    # 否则上面的断言即便实现有 bug 也可能因为两者恰好相等而白测。
    assert any(compound_crs[k] != naive_crs[k] for k in compound_crs), (
        "复合缩放与朴素缩放的期望值完全一致，这条测试对该 bug 没有区分度"
    )


def test_export_with_sidecar_writes_alongside_raw(running_server, tmp_path, sample_analysis):
    _request(running_server, "POST", "/api/looks", {"name": "sc", "analysis": sample_analysis})
    raw = tmp_path / "IMG_0001.CR3"
    raw.write_bytes(b"\x00fake")

    status, data = _request(running_server, "POST", "/api/looks/sc/export", {"sidecar": str(raw)})
    assert status == 200
    sidecar_path = Path(data["sidecar"])
    assert sidecar_path == raw.with_suffix(".xmp").resolve()
    assert sidecar_path.is_file()

    settings = xmp_reader.read_crs_settings(sidecar_path)
    assert "PresetType" not in settings  # sidecar 不是预设


def test_export_sidecar_missing_raw_returns_400(running_server, tmp_path, sample_analysis):
    _request(running_server, "POST", "/api/looks", {"name": "sc2", "analysis": sample_analysis})
    missing_raw = tmp_path / "NOPE.CR3"

    status, data = _request(
        running_server, "POST", "/api/looks/sc2/export", {"sidecar": str(missing_raw)}
    )
    assert status == 400
    assert "error" in data


def test_export_unknown_name_returns_404(running_server):
    status, data = _request(running_server, "POST", "/api/looks/nope/export", {})
    assert status == 404
    assert "error" in data


# ─── GET /report/<name> ─────────────────────────────────────────────────


def test_report_route_matches_render_report_output(running_server, sample_analysis):
    _request(running_server, "POST", "/api/looks", {"name": "rep", "analysis": sample_analysis})
    status, content_type, raw = _request_raw(running_server, "GET", "/report/rep")
    assert status == 200
    assert "text/html" in content_type

    html = raw.decode("utf-8")
    expected = report.render_report(intensity.scale_analysis(sample_analysis, 1.0), "rep")
    assert html == expected


def test_report_route_unknown_name_returns_404(running_server):
    status, content_type, raw = _request_raw(running_server, "GET", "/report/nope")
    assert status == 404
    assert "error" in json.loads(raw)


# ─── 静态结构 ────────────────────────────────────────────────────────────


def _static_text(rel: str) -> str:
    static_dir = Path(__file__).parent.parent / "looklift" / "gui" / "static"
    return (static_dir / rel).read_text(encoding="utf-8")


def test_looks_js_exists_and_referenced_in_index_html():
    static_dir = Path(__file__).parent.parent / "looklift" / "gui" / "static"
    assert (static_dir / "js" / "panels" / "looks.js").is_file()
    assert "/static/js/panels/looks.js" in _static_text("index.html")


def test_looks_js_opens_report_with_window_open():
    text = _static_text("js/panels/looks.js")
    assert "window.open(" in text
    assert "/report/" in text


def test_index_html_has_looks_grid_and_save_export_controls():
    text = _static_text("index.html")
    assert 'id="looks-grid"' in text
    assert 'id="looks-empty"' in text
    assert 'id="save-look-name"' in text
    assert 'id="save-look-btn"' in text
    assert 'id="export-preset-btn"' in text
    assert 'id="export-sidecar-path"' in text
    assert 'id="export-sidecar-btn"' in text
