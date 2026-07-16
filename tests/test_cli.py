import json

import pytest

from looklift import cli


def test_resolve_template_by_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    t = tmp_path / "x.json"
    t.write_text("{}")
    assert cli._resolve_template(str(t)) == t


def test_resolve_template_by_look_name(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    looks = tmp_path / "looks"
    looks.mkdir()
    (looks / "mystyle.json").write_text("{}")
    assert cli._resolve_template("mystyle").name == "mystyle.json"


def test_resolve_template_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(FileNotFoundError):
        cli._resolve_template("nope")


def test_expand_raws_glob(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for name in ("a.CR3", "b.CR3", "c.NEF"):
        (tmp_path / name).write_bytes(b"x")
    raws = cli._expand_raws(["*.CR3"])
    assert sorted(raws) == ["a.CR3", "b.CR3"]


def test_apply_end_to_end(tmp_path, monkeypatch, sample_analysis, capsys):
    monkeypatch.chdir(tmp_path)
    template = tmp_path / "look.json"
    template.write_text(json.dumps(sample_analysis), encoding="utf-8")
    raw = tmp_path / "IMG.CR3"
    raw.write_bytes(b"x")

    rc = cli.main(["apply", str(template), "--name", "MyLook", "--sidecar", str(raw)])
    assert rc == 0
    assert (tmp_path / "looks" / "MyLook.xmp").exists()
    assert (tmp_path / "IMG.xmp").exists()


def test_report_end_to_end(tmp_path, monkeypatch, sample_analysis):
    monkeypatch.chdir(tmp_path)
    template = tmp_path / "look.json"
    template.write_text(json.dumps(sample_analysis), encoding="utf-8")

    rc = cli.main(["report", str(template)])
    assert rc == 0
    html = (tmp_path / "look.html").read_text(encoding="utf-8")
    assert "<svg" in html and "风格分析" in html and "+0.35" in html
