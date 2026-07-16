"""GUI-T9：`POST /api/preview` 测试（U20 强度滑杆 + before/after 对比条，后端一半）。

覆盖 tasks.md T12 + design.md「强度缩放语义」GUI 侧用法 + 风险清单「大图内存」：
- factor=0 返回图应约等于输入缩略图（宽松逐像素比较——factor=0 时
  `intensity.scale_analysis` 把所有偏移量归零，等价于"无调整渲染"）；
- factor 越界（1.5 / -0.1）或类型不对（"abc"）→ 400；
- path 校验复用 T8 `_validate_image_path` 的断言（不存在 → 400）；
- 缺 analysis 字段 → 400；
- 3000px 宽输入 → 返回图长边 ≤2048（大图内存缓解）；
- content-type 为 image/jpeg；
- 新增的 binary-response 分发分支不破坏既有 JSON 路由（回归：/api/ping 仍是 JSON）。

静态结构：index.html 有 preview 卡容器/滑杆；panels/preview.js 含 clip-path 逻辑。
"""
from __future__ import annotations

import http.client
import io
import json
import threading
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from looklift.gui import server as gui_server


@pytest.fixture
def running_server():
    srv = gui_server.create_server(port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)


def _post_json_raw(srv, path: str, payload: dict):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
    try:
        body = json.dumps(payload).encode("utf-8")
        conn.request("POST", path, body=body, headers={"Content-Type": "application/json"})
        resp = conn.getresponse()
        raw = resp.read()
        return resp.status, resp.getheader("Content-Type"), raw
    finally:
        conn.close()


def _get_json(srv, path: str):
    conn = http.client.HTTPConnection("127.0.0.1", srv.server_port, timeout=5)
    try:
        conn.request("GET", path)
        resp = conn.getresponse()
        raw = resp.read()
        return resp.status, json.loads(raw)
    finally:
        conn.close()


def _make_jpeg(tmp_path: Path, name: str, size: tuple[int, int]) -> Path:
    """生成一张平滑渐变的合成 jpeg（不用纯色——纯色下 HSV 往返边界情况更多，
    渐变更贴近真实照片，也更能暴露"factor=0 应约等于原图"里的非平凡回归）。
    """
    path = tmp_path / name
    w, h = size
    arr = np.zeros((h, w, 3), dtype=np.uint8)
    arr[..., 0] = np.linspace(30, 220, w, dtype=np.uint8)[None, :]
    arr[..., 1] = np.linspace(220, 30, h, dtype=np.uint8)[:, None]
    arr[..., 2] = 120
    Image.fromarray(arr, "RGB").save(path, format="JPEG", quality=95)
    return path


# ─── factor=0 ≈ 原图 ──────────────────────────────────────────────────────


def test_preview_factor_zero_matches_input_thumbnail(running_server, tmp_path, sample_analysis):
    photo = _make_jpeg(tmp_path, "photo.jpg", (400, 300))
    status, content_type, raw = _post_json_raw(
        running_server,
        "/api/preview",
        {"path": str(photo), "analysis": sample_analysis, "factor": 0},
    )
    assert status == 200
    assert content_type == "image/jpeg"

    rendered = np.asarray(Image.open(io.BytesIO(raw)).convert("RGB"), dtype=np.int16)
    original = np.asarray(Image.open(photo).convert("RGB"), dtype=np.int16)
    assert rendered.shape == original.shape

    diff = np.abs(rendered - original)
    assert diff.mean() < 4, f"factor=0 预览与原图差异过大（均值 {diff.mean()}）"
    assert diff.max() < 30, f"factor=0 预览与原图存在离谱像素差异（max {diff.max()}）"


# ─── factor 校验 ───────────────────────────────────────────────────────────


@pytest.mark.parametrize("bad_factor", [1.5, -0.1, "abc"])
def test_preview_factor_out_of_range_or_wrong_type_returns_400(
    running_server, tmp_path, sample_analysis, bad_factor
):
    photo = _make_jpeg(tmp_path, "photo.jpg", (100, 100))
    status, content_type, raw = _post_json_raw(
        running_server,
        "/api/preview",
        {"path": str(photo), "analysis": sample_analysis, "factor": bad_factor},
    )
    assert status == 400
    assert "application/json" in content_type
    assert "error" in json.loads(raw)


def test_preview_missing_factor_returns_400(running_server, tmp_path, sample_analysis):
    photo = _make_jpeg(tmp_path, "photo.jpg", (100, 100))
    status, _, raw = _post_json_raw(
        running_server, "/api/preview", {"path": str(photo), "analysis": sample_analysis}
    )
    assert status == 400
    assert "error" in json.loads(raw)


# ─── path / analysis 校验 ──────────────────────────────────────────────────


def test_preview_nonexistent_path_returns_400(running_server, tmp_path, sample_analysis):
    missing = tmp_path / "not-there.jpg"
    status, _, raw = _post_json_raw(
        running_server,
        "/api/preview",
        {"path": str(missing), "analysis": sample_analysis, "factor": 1},
    )
    assert status == 400
    assert "error" in json.loads(raw)


def test_preview_missing_path_returns_400(running_server, sample_analysis):
    status, _, raw = _post_json_raw(
        running_server, "/api/preview", {"analysis": sample_analysis, "factor": 1}
    )
    assert status == 400
    assert "error" in json.loads(raw)


def test_preview_missing_analysis_returns_400(running_server, tmp_path):
    photo = _make_jpeg(tmp_path, "photo.jpg", (100, 100))
    status, _, raw = _post_json_raw(running_server, "/api/preview", {"path": str(photo), "factor": 1})
    assert status == 400
    assert "error" in json.loads(raw)


# ─── 大图内存缓解:统一缩到长边 2048 ─────────────────────────────────────


def test_preview_large_image_downscaled_to_max_edge(running_server, tmp_path, sample_analysis):
    photo = _make_jpeg(tmp_path, "big.jpg", (3000, 2000))
    status, _, raw = _post_json_raw(
        running_server,
        "/api/preview",
        {"path": str(photo), "analysis": sample_analysis, "factor": 1},
    )
    assert status == 200
    rendered = Image.open(io.BytesIO(raw))
    assert max(rendered.size) <= 2048
    assert rendered.size[0] / rendered.size[1] == pytest.approx(3000 / 2000, rel=0.02)


# ─── content-type ──────────────────────────────────────────────────────────


def test_preview_content_type_is_jpeg(running_server, tmp_path, sample_analysis):
    photo = _make_jpeg(tmp_path, "photo.jpg", (100, 100))
    status, content_type, raw = _post_json_raw(
        running_server, "/api/preview", {"path": str(photo), "analysis": sample_analysis, "factor": 1}
    )
    assert status == 200
    assert content_type == "image/jpeg"
    assert Image.open(io.BytesIO(raw)).format == "JPEG"


# ─── 回归:binary-response 分支不破坏既有 JSON 路由 ─────────────────────────


def test_binary_response_branch_does_not_break_ping_json_route(running_server):
    status, data = _get_json(running_server, "/api/ping")
    assert status == 200
    assert data == {"ok": True}


# ─── 静态结构 ────────────────────────────────────────────────────────────


def _static_text(rel: str) -> str:
    static_dir = Path(__file__).parent.parent / "looklift" / "gui" / "static"
    return (static_dir / rel).read_text(encoding="utf-8")


def test_index_html_has_preview_card_and_slider():
    text = _static_text("index.html")
    assert 'id="preview-card"' in text
    assert 'id="preview-before"' in text
    assert 'id="preview-after"' in text
    assert 'id="preview-intensity-slider"' in text
    assert 'type="range"' in text
    assert 'id="preview-intensity-value"' in text


def test_index_html_references_preview_js():
    assert "/static/js/panels/preview.js" in _static_text("index.html")


def test_preview_js_contains_clip_path_logic():
    text = _static_text("js/panels/preview.js")
    assert "clip-path" in text
    assert "clipPath" in text
    assert "currentFactor" in text
