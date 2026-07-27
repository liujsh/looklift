import json

import numpy as np
import pytest

from looklift import raw_gate, raw_gate_runtime


def _manifest(tmp_path, count=5):
    samples = []
    for index in range(count):
        source = tmp_path / f"sample-{index}.raw"
        source.write_bytes(b"raw")
        samples.append({"path": str(source), "camera": f"相机-{index}"})
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"samples": samples}, ensure_ascii=False), encoding="utf-8")
    return manifest, samples


def test_load_manifest_rejects_duplicate_paths_and_missing_camera(tmp_path):
    manifest = tmp_path / "bad.json"
    manifest.write_text(json.dumps({"samples": [{"path": "a.raw", "camera": "A"}, {"path": "a.raw", "camera": "B"}]}), encoding="utf-8")

    with pytest.raises(raw_gate.ManifestError, match="重复"):
        raw_gate.load_manifest(manifest)

    manifest.write_text(json.dumps({"samples": [{"path": "a.raw"}]}), encoding="utf-8")
    with pytest.raises(raw_gate.ManifestError, match="camera"):
        raw_gate.load_manifest(manifest)


def test_gate_go_requires_coverage_pipeline_and_measurements(tmp_path):
    manifest, samples = _manifest(tmp_path)

    def decoder(path):
        shape = (6325, 6325, 3) if path.name == "sample-4.raw" else (4000, 6000, 3)
        return raw_gate.DecodedRaw(
            rgb=np.zeros(shape, dtype=np.uint16),
            orientation="normal",
            white_balance_checked=True,
        )

    report = raw_gate.run_gate(
        manifest,
        decoder=decoder,
        memory_measure=lambda: 768.0,
        pipeline_check=lambda rgb: rgb.shape[-1] == 3,
    )

    assert report["decision"] == "GO"
    assert report["coverage"]["cameras"] == 5
    assert all(item["status"] == "ok" for item in report["samples"])
    assert report["pipeline"]["compatible"] is True
    assert {item["path"] for item in report["samples"]} == {str(tmp_path / f"sample-{i}.raw") for i in range(5)}


def test_gate_isolates_bad_sample_and_returns_no_go(tmp_path):
    manifest, samples = _manifest(tmp_path)

    def decoder(path):
        if path.name == "sample-2.raw":
            raise ValueError("损坏 RAW")
        return raw_gate.DecodedRaw(
            rgb=np.zeros((3000, 4000, 3), dtype=np.uint16),
            orientation="normal",
            white_balance_checked=True,
        )

    report = raw_gate.run_gate(
        manifest,
        decoder=decoder,
        memory_measure=lambda: 768.0,
        pipeline_check=lambda _rgb: True,
    )

    assert report["decision"] == "NO-GO"
    failed = next(item for item in report["samples"] if item["path"] == samples[2]["path"])
    assert failed["status"] == "error"
    assert failed["error"]["code"] == "decode_failed"
    assert sum(item["status"] == "ok" for item in report["samples"]) == 4
    assert report["reason"] == "sample_failed"


def test_missing_rawpy_is_structured_no_go_and_report_is_writable(tmp_path, monkeypatch):
    manifest, _ = _manifest(tmp_path)
    monkeypatch.setattr(raw_gate, "load_rawpy_decoder", lambda: (None, "rawpy_unavailable"))
    output = tmp_path / "raw-gate-report.json"

    report = raw_gate.run_gate(manifest, decoder=None)
    raw_gate.write_report(report, output)

    assert report["decision"] == "NO-GO"
    assert report["environment"]["rawpy"] == "unavailable"
    assert report["reason"] == "rawpy_unavailable"
    assert json.loads(output.read_text(encoding="utf-8"))["decision"] == "NO-GO"
    assert "降级" in raw_gate.render_summary(report)


def test_default_pipeline_check_accepts_rawpy_uint16_rgb():
    rgb = np.full((4, 6, 3), 32768, dtype=np.uint16)

    assert raw_gate.default_pipeline_check(rgb) is True


def test_gate_reports_pipeline_failure_before_derived_coverage(tmp_path):
    manifest, _ = _manifest(tmp_path)

    def decoder(_path):
        return raw_gate.DecodedRaw(
            rgb=np.zeros((6325, 6325, 3), dtype=np.uint16),
            orientation="normal",
            white_balance_checked=True,
        )

    report = raw_gate.run_gate(
        manifest,
        decoder=decoder,
        memory_measure=lambda: 768.0,
        pipeline_check=lambda _rgb: False,
    )

    assert report["reason"] == "pipeline_incompatible"


def test_resource_peak_memory_units_follow_platform_contract():
    assert raw_gate_runtime._resource_peak_mb(2 * 1024 * 1024, "linux") == 2048.0
    assert raw_gate_runtime._resource_peak_mb(2 * 1024 * 1024 * 1024, "darwin") == 2048.0
