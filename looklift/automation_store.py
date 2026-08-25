"""自动化技能、待确认计划与运行清单的本地持久化。"""
from __future__ import annotations

import copy
import json
import os
import re
import threading
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config, xmp_writer

SUPPORTED_INPUTS = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_FORBIDDEN_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


class AutomationStore:
    """用独立 JSON 文件保存小规模技能、计划和运行记录。"""

    def __init__(self, root: str | Path | None = None):
        self.root = Path(root) if root is not None else config.CONFIG_PATH.parent / "automation"
        self._io_lock = threading.RLock()

    def create_workflow(
        self,
        *,
        name: Any,
        look_name: Any,
        factor: Any,
        suffix: Any,
        quality: Any,
    ) -> dict[str, Any]:
        clean_name = _text(name, "技能名称", 60)
        clean_look = _text(look_name, "风格名称", 100)
        clean_factor = _factor(factor)
        clean_suffix = _suffix(suffix)
        clean_quality = _quality(quality)
        if any(item["name"].casefold() == clean_name.casefold() for item in self.list_workflows()):
            raise ValueError(f"已存在同名自动化技能：{clean_name}")
        workflow = {
            "id": uuid.uuid4().hex,
            "name": clean_name,
            "look_name": clean_look,
            "factor": clean_factor,
            "suffix": clean_suffix,
            "quality": clean_quality,
            "created_at": _now(),
        }
        self._write(self._path("workflows", workflow["id"]), workflow)
        return workflow

    def list_workflows(self) -> list[dict[str, Any]]:
        return self._list("workflows")

    def get_workflow(self, workflow_id: str) -> dict[str, Any] | None:
        return self._read(self._path("workflows", workflow_id))

    def delete_workflow(self, workflow_id: str) -> bool:
        path = self._path("workflows", workflow_id)
        try:
            path.unlink()
        except FileNotFoundError:
            return False
        return True

    def create_plan(
        self,
        workflow: dict[str, Any],
        analysis: dict[str, Any],
        inputs: list[str],
        output_dir: str,
    ) -> dict[str, Any]:
        if not isinstance(inputs, list) or not inputs or len(inputs) > 1000:
            raise ValueError("输入照片必须为 1–1000 个路径")
        if not isinstance(analysis, dict):
            raise ValueError("风格参数必须是对象")
        # 复用 XMP 白盒映射的数值校验，避免把坏参数冻结进后台任务。
        xmp_writer.analysis_to_crs(analysis)
        output_root = Path(output_dir).expanduser().resolve()
        if not output_root.is_dir():
            raise ValueError(f"输出目录不存在或不是目录：{output_root}")

        items: list[dict[str, Any]] = []
        for raw in inputs:
            source = Path(str(raw)).expanduser().resolve()
            output = output_root / f"{source.stem}{workflow['suffix']}.jpg"
            error = None
            status = "ready"
            if not source.is_file():
                status, error = "invalid", f"输入文件不存在：{source}"
            elif source.suffix.lower() not in SUPPORTED_INPUTS:
                status, error = "invalid", f"当前不支持此输入格式：{source.suffix or '无扩展名'}"
            elif output.resolve() == source:
                status, error = "conflict", "输出路径不能与输入文件相同"
            elif output.exists():
                status, error = "conflict", f"输出文件已存在：{output}"
            items.append({
                "source": str(source),
                "output": str(output),
                "status": status,
                "error": error,
            })

        output_counts = Counter(item["output"].casefold() for item in items)
        for item in items:
            if output_counts[item["output"].casefold()] > 1:
                item["status"] = "conflict"
                item["error"] = f"同批输出重名：{item['output']}"

        plan = {
            "id": uuid.uuid4().hex,
            "workflow": copy.deepcopy(workflow),
            "analysis": copy.deepcopy(analysis),
            "output_dir": str(output_root),
            "ready": all(item["status"] == "ready" for item in items),
            "created_at": _now(),
            "items": items,
        }
        self._write(self._path("plans", plan["id"]), plan)
        return plan

    def get_plan(self, plan_id: str) -> dict[str, Any] | None:
        return self._read(self._path("plans", plan_id))

    def save_run(self, run: dict[str, Any]) -> None:
        self._write(self._path("runs", str(run["id"])), run)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self._read(self._path("runs", run_id))

    def list_runs(self) -> list[dict[str, Any]]:
        return self._list("runs", reverse=True)

    def _list(self, kind: str, *, reverse: bool = False) -> list[dict[str, Any]]:
        directory = self.root / kind
        if not directory.is_dir():
            return []
        entries = []
        for path in directory.glob("*.json"):
            value = self._read(path)
            if isinstance(value, dict):
                entries.append(value)
        return sorted(entries, key=lambda item: item.get("created_at", ""), reverse=reverse)

    def _path(self, kind: str, item_id: str) -> Path:
        if not isinstance(item_id, str) or not _SAFE_ID.fullmatch(item_id):
            raise ValueError("自动化记录 ID 无效")
        return self.root / kind / f"{item_id}.json"

    def _read(self, path: Path) -> dict[str, Any] | None:
        with self._io_lock:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except FileNotFoundError:
                return None
            except (OSError, json.JSONDecodeError):
                return None
            return value if isinstance(value, dict) else None

    def _write(self, path: Path, value: dict[str, Any]) -> None:
        with self._io_lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            try:
                temporary.write_text(
                    json.dumps(value, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)


def _text(value: Any, label: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label}不能为空")
    clean = value.strip()
    if len(clean) > maximum or _FORBIDDEN_FILENAME.search(clean):
        raise ValueError(f"{label}包含不支持的字符或过长")
    return clean


def _factor(value: Any) -> float:
    if isinstance(value, bool):
        raise ValueError("技能强度必须在 0–1 之间")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError("技能强度必须在 0–1 之间") from None
    if not 0 <= result <= 1:
        raise ValueError("技能强度必须在 0–1 之间")
    return result


def _suffix(value: Any) -> str:
    clean = _text(value, "输出后缀", 32)
    if clean in {".", ".."} or not clean.startswith("-"):
        raise ValueError("输出后缀必须以短横线开头")
    return clean


def _quality(value: Any) -> int:
    if isinstance(value, bool):
        raise ValueError("JPEG 质量必须是 60–100 的整数")
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError("JPEG 质量必须是 60–100 的整数") from None
    if not 60 <= result <= 100 or isinstance(value, float) and not value.is_integer():
        raise ValueError("JPEG 质量必须是 60–100 的整数")
    return result


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
