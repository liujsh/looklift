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


def builtin_looks_dir() -> Path:
    """返回随包分发的只读内置模板目录。"""
    return Path(__file__).resolve().parents[1] / "data" / "looks"


def json_path(looks_dir: Path, name: str) -> Path:
    return looks_dir / f"{name}.json"


def xmp_path(looks_dir: Path, name: str) -> Path:
    return looks_dir / f"{name}.xmp"


def exists(looks_dir: Path | None, name: str, builtins_dir: Path | None = None) -> bool:
    """名字是否已被占用（收藏前的重名检查用）。"""
    builtins = builtin_looks_dir() if builtins_dir is None else builtins_dir
    return bool(
        (looks_dir is not None and json_path(looks_dir, name).is_file())
        or json_path(builtins, name).is_file()
    )


def _write_preset_from_crs(looks_dir: Path, name: str, crs: dict[str, Any]) -> Path:
    looks_dir.mkdir(parents=True, exist_ok=True)
    return xmp_writer.write_preset(crs, name, xmp_path(looks_dir, name))


def _write_preset(looks_dir: Path, name: str, analysis: dict[str, Any]) -> Path:
    return _write_preset_from_crs(looks_dir, name, xmp_writer.analysis_to_crs(analysis))


def save(
    looks_dir: Path,
    name: str,
    analysis: dict[str, Any],
    builtins_dir: Path | None = None,
) -> None:
    """收藏一个风格：落盘 `<name>.json`（`analysis` 应该是调用方已经按当前
    滑杆强度 `intensity.scale_analysis` 缩放过的结果——这里不做缩放，只管
    写）+ 对应的 `<name>.xmp` 预设。调用方需自行做好重名校验，这里不检查、
    不静默覆盖（`Path.write_text` 本身就是覆盖写，交给调用方在写之前挡住）。

    fold-in 修复（v0.4 收尾）：`analysis_to_crs` 提前到任何落盘动作之前调用
    ——若 `analysis` 混进非数值字段（如 `basic.exposure = "x"`），这里会在
    两个文件都还没写之前就抛出 `ValueError`，不会出现"json 已落盘、xmp 报错
    半路失败"的孤儿文件；`lookstore.exists()` 只看 `.json` 是否存在，孤儿
    json 会让这个名字永久占用、重试同一个名字会被 `POST /api/looks` 的 409
    重名检查挡死，用户没有任何办法恢复。
    """
    builtins = builtin_looks_dir() if builtins_dir is None else builtins_dir
    if json_path(builtins, name).is_file():
        raise PermissionError(f"内置模板只读，不能覆盖：{name}")
    crs = xmp_writer.analysis_to_crs(analysis)
    looks_dir.mkdir(parents=True, exist_ok=True)
    json_path(looks_dir, name).write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    _write_preset_from_crs(looks_dir, name, crs)


def load(
    looks_dir: Path | None,
    name: str,
    builtins_dir: Path | None = None,
) -> dict[str, Any] | None:
    """读取完整 analysis；历史用户同名条目优先于内置模板。"""
    builtins = builtin_looks_dir() if builtins_dir is None else builtins_dir
    candidates = [] if looks_dir is None else [json_path(looks_dir, name)]
    candidates.append(json_path(builtins, name))
    for path in candidates:
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    return None


def export_preset(looks_dir: Path, name: str, analysis: dict[str, Any]) -> Path:
    """按给定的（可能已经按导出请求里的 `factor` 重新缩放过的）analysis 重新
    生成库内同名 `.xmp` 预设，返回写出的路径（调用方负责转成绝对路径返回给
    前端——`config.looks_dir()` 在 cwd 有 `looks/` 时返回相对路径，直接吐给
    前端没意义，用户看不出这是相对谁的相对路径）。
    """
    return _write_preset(looks_dir, name, analysis)


def _list_source(directory: Path | None, source: str) -> list[dict[str, Any]]:
    if directory is None or not directory.is_dir():
        return []
    entries: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
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
            "has_preset": xmp_path(directory, path.stem).is_file(),
            "source": source,
            "readonly": source == "built_in",
        })
    return entries


def list_entries(
    looks_dir: Path | None,
    builtins_dir: Path | None = None,
) -> list[dict[str, Any]]:
    """列出风格库条目：`[{name, summary, has_preset}]`。

    损坏的 json（解析失败、或顶层不是对象）静默跳过，不让一个坏文件炸掉
    整个列表——与 `cli.cmd_list` 对同一目录的容错口径一致。`summary` 截断到
    `_SUMMARY_MAX_CHARS` 字符（卡片网格里不需要完整摘要）。
    """
    builtins = builtin_looks_dir() if builtins_dir is None else builtins_dir
    merged = {entry["name"]: entry for entry in _list_source(builtins, "built_in")}
    # 兼容早期版本已经存在的同名用户条目：用户数据优先，且不显示重复卡片。
    merged.update({entry["name"]: entry for entry in _list_source(looks_dir, "user")})
    return sorted(merged.values(), key=lambda entry: entry["name"])
