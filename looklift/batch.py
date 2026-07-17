"""按一级子目录批量分析同风格照片，并以结果文件断点续跑。"""
from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import analyzer

RESULT_NAME = ".looklift-result.json"
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}

AnalyzeFn = Callable[..., dict[str, Any]]
ProgressFn = Callable[[str, int, int, Path, str | None], None]


@dataclass(frozen=True)
class BatchGroup:
    """一个目录及其中用于共同风格分析的照片。"""

    path: Path
    images: list[Path]


@dataclass
class BatchResult:
    """一次批量运行的统计与失败摘要。"""

    total: int
    completed: int = 0
    skipped: int = 0
    failures: dict[str, str] = field(default_factory=dict)

    @property
    def failed(self) -> int:
        return len(self.failures)


def scan_groups(root: str | Path) -> list[BatchGroup]:
    """扫描含图片的一级子目录；组按名称、图片按 mtime/名称稳定排序。"""
    root_path = Path(root)
    if not root_path.is_dir():
        raise FileNotFoundError(f"批量目录不存在或不是目录：{root_path}")

    groups: list[BatchGroup] = []
    for directory in sorted((path for path in root_path.iterdir() if path.is_dir()), key=_name_key):
        images = [
            path for path in directory.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ]
        images.sort(key=lambda path: (path.stat().st_mtime_ns, path.name.casefold(), path.name))
        if images:
            groups.append(BatchGroup(directory, images[:5]))
    return groups


def run_batch(
    root: str | Path,
    *,
    analyze: AnalyzeFn = analyzer.analyze,
    style_hint: str | None = None,
    backend: str = "auto",
    force: bool = False,
    on_progress: ProgressFn | None = None,
) -> BatchResult:
    """逐组分析；成功结果原子落盘，失败不中断后续组。"""
    groups = scan_groups(root)
    result = BatchResult(total=len(groups))

    for index, group in enumerate(groups, 1):
        output = group.path / RESULT_NAME
        temporary = output.with_name(output.name + ".tmp")
        if output.exists() and not force:
            result.skipped += 1
            _notify(on_progress, "skipped", index, len(groups), group.path)
            continue

        _notify(on_progress, "started", index, len(groups), group.path)
        try:
            if force:
                output.unlink(missing_ok=True)
            temporary.unlink(missing_ok=True)
            analysis = analyze(group.images, style_hint=style_hint, backend=backend)
            temporary.write_text(
                json.dumps(analysis, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(temporary, output)
        except Exception as exc:  # noqa: BLE001 - 单组失败必须汇总后继续
            temporary.unlink(missing_ok=True)
            result.failures[group.path.name] = str(exc)
            _notify(on_progress, "failed", index, len(groups), group.path, str(exc))
            continue

        result.completed += 1
        _notify(on_progress, "completed", index, len(groups), group.path)

    return result


def _name_key(path: Path) -> tuple[str, str]:
    return path.name.casefold(), path.name


def _notify(
    callback: ProgressFn | None,
    event: str,
    index: int,
    total: int,
    group: Path,
    detail: str | None = None,
) -> None:
    if callback is not None:
        callback(event, index, total, group, detail)
