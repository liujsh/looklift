import pytest

from looklift import analyzer
from looklift.analyzer import _extract_json, _normalize, resolve_backend


def test_normalize_fills_sparse_output():
    sparse = {"summary": "x", "basic": {"contrast": 20},
              "hsl": [{"color": "blue", "saturation": 15}]}
    full = _normalize(sparse)
    assert full["basic"]["exposure"] == 0
    assert full["basic"]["contrast"] == 20
    assert full["hsl"][0]["hue"] == 0
    assert full["color_grading"]["shadows"]["saturation"] == 0
    assert full["color_grading"]["blending"] == 50
    assert full["effects"]["grain_amount"] == 0
    assert full["tone_curve"] == []


def test_normalize_drops_malformed_curve_points():
    out = _normalize({"tone_curve": [{"input": 0, "output": 0}, {"bad": 1}, "junk"]})
    assert out["tone_curve"] == [{"input": 0, "output": 0}]


@pytest.mark.parametrize("text", [
    '{"a": 1}',
    '```json\n{"a": 1}\n```',
    '好的,分析结果如下:\n{"a": 1}\n以上。',
])
def test_extract_json_variants(text):
    assert _extract_json(text) == {"a": 1}


def test_extract_json_failure():
    with pytest.raises(ValueError):
        _extract_json("没有任何 JSON")


def test_resolve_backend_api_when_key_set(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert resolve_backend("auto") == "api"


def test_resolve_backend_cli_fallback(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("shutil.which", lambda _: "/usr/bin/claude")
    assert resolve_backend("auto") == "cli"


def test_resolve_backend_none_available(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("shutil.which", lambda _: None)
    with pytest.raises(RuntimeError):
        resolve_backend("auto")


def test_analyze_rejects_too_many_images():
    with pytest.raises(ValueError, match="最多"):
        analyzer.analyze([f"{i}.jpg" for i in range(6)])


def test_analyze_rejects_multi_with_original():
    with pytest.raises(ValueError, match="original"):
        analyzer.analyze(["a.jpg", "b.jpg"], original="raw.jpg")
