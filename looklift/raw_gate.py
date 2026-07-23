"""RAW 可行性门：离线样本解码、测量与 GO/NO-GO 报告。"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

import numpy as np

from .raw_gate_runtime import load_rawpy_decoder, measure_memory_mb
from .raw_gate_types import DecodedRaw

MIN_SAMPLES = 5
MAX_MEMORY_MB = 2048.0
MAX_DECODE_SECONDS_24MP = 5.0
MAX_DECODE_SECONDS_40MP = 10.0


class ManifestError(ValueError):
    """RAW manifest 不符合离线探针契约。"""


@dataclass(frozen=True)
class SampleSpec:
    path: Path
    camera: str
    label: str = ""


def load_manifest(path: Path) -> tuple[SampleSpec, ...]:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ManifestError(f"manifest 读取失败：{exc}") from exc
    samples = payload.get("samples") if isinstance(payload, dict) else None
    if not isinstance(samples, list) or not samples:
        raise ManifestError("manifest.samples 必须是非空数组")
    result: list[SampleSpec] = []
    seen: set[str] = set()
    for index, item in enumerate(samples):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ManifestError(f"samples[{index}].path 必须是字符串")
        camera = item.get("camera")
        if not isinstance(camera, str) or not camera.strip():
            raise ManifestError(f"samples[{index}].camera 必须是非空字符串")
        resolved = str(Path(item["path"]).expanduser().resolve(strict=False))
        normalized = os.path.normcase(resolved)
        if normalized in seen:
            raise ManifestError(f"manifest 包含重复样本路径：{resolved}")
        seen.add(normalized)
        label = item.get("label", "")
        if not isinstance(label, str):
            raise ManifestError(f"samples[{index}].label 必须是字符串")
        result.append(SampleSpec(Path(resolved), camera.strip(), label.strip()))
    return tuple(result)


def run_gate(
    manifest: Path | Iterable[SampleSpec],
    *,
    decoder: Callable[[Path], DecodedRaw] | None = None,
    memory_measure: Callable[[], float | None] | None = None,
    pipeline_check: Callable[[Any], bool] | None = None,
) -> dict[str, Any]:
    samples = load_manifest(manifest) if isinstance(manifest, (str, Path)) else tuple(manifest)
    if not samples:
        raise ManifestError("样本清单不能为空")
    rawpy_decoder, rawpy_reason = (decoder, None) if decoder is not None else load_rawpy_decoder()
    report: dict[str, Any] = {
        "decision": "NO-GO",
        "reason": rawpy_reason,
        "environment": {"rawpy": "available" if rawpy_decoder else "unavailable"},
        "coverage": {
            "samples": len(samples),
            "cameras": len({sample.camera for sample in samples}),
            "has_24mp": False,
            "has_40mp": False,
        },
        "performance": {"measurements_available": memory_measure is not None, "max_memory_mb": MAX_MEMORY_MB},
        "pipeline": {"compatible": False, "checked": False},
        "samples": [],
        "fallback": "内嵌 JPEG 预览 + XMP sidecar",
    }
    if rawpy_decoder is None:
        report["samples"] = [_skipped_sample(sample, rawpy_reason or "rawpy_unavailable") for sample in samples]
        return report

    measure = memory_measure or measure_memory_mb
    check_pipeline = pipeline_check or default_pipeline_check
    results: list[dict[str, Any]] = []
    pipeline_ok = True
    for sample in samples:
        result = _probe_sample(sample, rawpy_decoder, measure, check_pipeline)
        results.append(result)
        pipeline_ok = pipeline_ok and result["pipeline_compatible"]
    report["samples"] = results
    report["pipeline"] = {"compatible": pipeline_ok, "checked": True}
    report["coverage"]["has_24mp"] = any(
        (item.get("width") or 0) * (item.get("height") or 0) >= 24_000_000
        for item in results
    )
    report["coverage"]["has_40mp"] = any(
        (item.get("width") or 0) * (item.get("height") or 0) >= 40_000_000
        for item in results
    )
    report["performance"]["measurements_available"] = all(
        result["peak_memory_mb"] is not None for result in results if result["status"] == "ok"
    )
    failed = [result for result in results if result["status"] != "ok"]
    performance_failed = any(result.get("performance_pass") is False for result in results)
    if (
        len(samples) < MIN_SAMPLES
        or len({sample.camera for sample in samples}) < MIN_SAMPLES
        or not report["coverage"]["has_24mp"]
        or not report["coverage"]["has_40mp"]
    ):
        report["reason"] = "sample_coverage"
    elif failed:
        report["reason"] = "sample_failed"
    elif not pipeline_ok:
        report["reason"] = "pipeline_incompatible"
    elif not report["performance"]["measurements_available"]:
        report["reason"] = "measurement_unavailable"
    elif performance_failed:
        report["reason"] = "performance_threshold"
    else:
        report["decision"] = "GO"
        report["reason"] = "all_gates_passed"
        report["fallback"] = None
    return report


def write_report(report: dict[str, Any], path: Path) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, destination)


def render_summary(report: dict[str, Any]) -> str:
    decision = report.get("decision", "NO-GO")
    reason = report.get("reason") or "unknown"
    coverage = report.get("coverage", {})
    if decision == "GO":
        next_step = "后续 v2.3-B 可采用 RAW 全解码路径。"
    else:
        next_step = "后续 v2.3-B 必须采用内嵌 JPEG 预览 + XMP sidecar 降级路径。"
    return (
        f"RAW 可行性门：{decision}\n"
        f"样本覆盖：{coverage.get('samples', 0)} 个，{coverage.get('cameras', 0)} 种相机\n"
        f"原因：{reason}\n{next_step}"
    )


def default_pipeline_check(rgb: Any) -> bool:
    from PIL import Image

    image = Image.fromarray(rgb)
    return image.mode == "RGB"


def _probe_sample(
    sample: SampleSpec,
    decoder: Callable[[Path], DecodedRaw],
    memory_measure: Callable[[], float | None],
    pipeline_check: Callable[[Any], bool],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "path": str(sample.path), "camera": sample.camera, "label": sample.label,
        "status": "error", "error": None, "decode_ms": None, "peak_memory_mb": None,
        "width": None, "height": None, "channels": None, "dtype": None,
        "orientation": None, "white_balance_checked": False,
        "pipeline_compatible": False, "performance_pass": None,
    }
    if not sample.path.is_file():
        result["error"] = {"code": "missing_file", "message": "样本文件不存在"}
        return result
    started = time.perf_counter()
    try:
        decoded = decoder(sample.path)
        array = np.asarray(decoded.rgb)
        _validate_output(array, decoded)
        try:
            pipeline_ok = bool(pipeline_check(decoded.rgb))
        except Exception as exc:  # noqa: BLE001 —— 管线失败归类为当前样本不兼容
            raise _ProbeError("pipeline_incompatible", f"现有图像管线检查异常：{exc}") from exc
        if not pipeline_ok:
            raise _ProbeError("pipeline_incompatible", "解码结果无法进入现有图像管线")
    except _ProbeError as exc:
        result["error"] = {"code": exc.code, "message": str(exc)}
        return result
    except Exception as exc:  # noqa: BLE001 —— 单个坏样本不能中断整份报告
        result["error"] = {"code": "decode_failed", "message": str(exc)}
        return result
    elapsed = time.perf_counter() - started
    try:
        memory = memory_measure()
    except Exception:  # noqa: BLE001 —— 平台测量失败不能中断其余样本
        memory = None
    height, width, channels = array.shape
    result.update({
        "status": "ok", "decode_ms": round(elapsed * 1000, 2),
        "peak_memory_mb": round(memory, 2) if memory is not None else None,
        "width": width, "height": height, "channels": channels,
        "dtype": str(array.dtype), "orientation": decoded.orientation,
        "white_balance_checked": decoded.white_balance_checked,
        "pipeline_compatible": True,
        "performance_pass": _performance_pass(width * height, elapsed, memory),
    })
    return result


def _validate_output(array: np.ndarray, decoded: DecodedRaw) -> None:
    if array.ndim != 3 or array.shape[2] != 3:
        raise _ProbeError("output_shape", "解码结果必须是 H×W×3 RGB")
    if array.dtype.kind != "u" or array.dtype.itemsize not in {1, 2}:
        raise _ProbeError("output_dtype", "解码结果必须是 8/16 位无符号 RGB")
    if decoded.orientation not in {"normal", "camera"}:
        raise _ProbeError("orientation_unchecked", "无法确认 RAW 方向")
    if not decoded.white_balance_checked:
        raise _ProbeError("white_balance_unchecked", "无法确认相机白平衡已参与解码")


def _performance_pass(pixels: int, elapsed: float, memory: float | None) -> bool:
    if memory is None or memory > MAX_MEMORY_MB:
        return False
    limit = MAX_DECODE_SECONDS_40MP if pixels >= 40_000_000 else MAX_DECODE_SECONDS_24MP
    return elapsed <= limit


def _skipped_sample(sample: SampleSpec, code: str) -> dict[str, Any]:
    return {
        "path": str(sample.path), "camera": sample.camera, "label": sample.label,
        "status": "skipped", "error": {"code": code, "message": "rawpy 不可用，未执行解码"},
    }


class _ProbeError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


if __name__ == "__main__":
    from .raw_gate_cli import main

    raise SystemExit(main())
