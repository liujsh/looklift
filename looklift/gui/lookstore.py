"""风格库文件 IO：列出 / 读取 / 落盘 / 导出风格库里的 json + xmp 条目。

从 `api.py` 拆出来——`api.py` 按项目分层约定只做「HTTP 参数 → 核心调用 →
JSON 响应」的粘合，这里的目录遍历、损坏 json 容错、路径拼装属于实现细节，
不该堆进 handler（见 CLAUDE.md 分层规范：单文件职责单一）。本模块不碰 HTTP
层（不知道 status code），`api.py` 的 looks 系列 handler 负责把这里的返回值
/ 缺失情况翻译成 HTTP 响应。

落盘形状与 CLI（`cli.py` 的 `cmd_analyze`/`cmd_list`）保持一致：`<name>.json`
是 `analysis` 原样序列化（`ensure_ascii=False, indent=2`），`<name>.xmp` 是
对应的 Lightroom 预设，`has_preset` 靠 `.xmp` 是否存在判断——GUI 和 CLI 读
同一份风格库目录，形状不一致会导致互相看不懂对方存的东西。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import xmp_writer

_SUMMARY_MAX_CHARS = 80


def json_path(looks_dir: Path, name: str) -> Path:
    return looks_dir / f"{name}.json"


def xmp_path(looks_dir: Path, name: str) -> Path:
    return looks_dir / f"{name}.xmp"


def exists(looks_dir: Path, name: str) -> bool:
    """名字是否已被占用（收藏前的重名检查用）。"""
    return json_path(looks_dir, name).is_file()


def _write_preset(looks_dir: Path, name: str, analysis: dict[str, Any]) -> Path:
    looks_dir.mkdir(parents=True, exist_ok=True)
    crs = xmp_writer.analysis_to_crs(analysis)
    return xmp_writer.write_preset(crs, name, xmp_path(looks_dir, name))


def save(looks_dir: Path, name: str, analysis: dict[str, Any]) -> None:
    """收藏一个风格：落盘 `<name>.json`（`analysis` 应该是调用方已经按当前
    滑杆强度 `intensity.scale_analysis` 缩放过的结果——这里不做缩放，只管
    写）+ 对应的 `<name>.xmp` 预设。调用方需自行做好重名校验，这里不检查、
    不静默覆盖（`Path.write_text` 本身就是覆盖写，交给调用方在写之前挡住）。
    """
    looks_dir.mkdir(parents=True, exist_ok=True)
    json_path(looks_dir, name).write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_preset(looks_dir, name, analysis)


def load(looks_dir: Path, name: str) -> dict[str, Any] | None:
    """读取某个风格的完整 analysis；不存在返回 `None`。"""
    path = json_path(looks_dir, name)
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def export_preset(looks_dir: Path, name: str, analysis: dict[str, Any]) -> Path:
    """按给定的（可能已经按导出请求里的 `factor` 重新缩放过的）analysis 重新
    生成库内同名 `.xmp` 预设，返回写出的路径（调用方负责转成绝对路径返回给
    前端——`config.looks_dir()` 在 cwd 有 `looks/` 时返回相对路径，直接吐给
    前端没意义，用户看不出这是相对谁的相对路径）。
    """
    return _write_preset(looks_dir, name, analysis)


def list_entries(looks_dir: Path) -> list[dict[str, Any]]:
    """列出风格库条目：`[{name, summary, has_preset}]`。

    损坏的 json（解析失败、或顶层不是对象）静默跳过，不让一个坏文件炸掉
    整个列表——与 `cli.cmd_list` 对同一目录的容错口径一致。`summary` 截断到
    `_SUMMARY_MAX_CHARS` 字符（卡片网格里不需要完整摘要）。
    """
    if not looks_dir.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(looks_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        summary = data.get("summary") or ""
        if len(summary) > _SUMMARY_MAX_CHARS:
            summary = summary[:_SUMMARY_MAX_CHARS] + "…"
        entries.append({
            "name": path.stem,
            "summary": summary,
            "has_preset": xmp_path(looks_dir, path.stem).is_file(),
        })
    return entries
