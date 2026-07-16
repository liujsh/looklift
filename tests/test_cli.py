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
    (tmp_path / "looks").mkdir()  # cwd 已有 looks/,config.looks_dir() 按 cwd 优先规则选中它
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


def test_resolve_template_uses_global_looks(monkeypatch, tmp_path, sample_analysis):
    """cwd 无 looks/ 时,模版名字应在全局库(config.looks_dir())中解析。"""
    import json
    from looklift import cli, config
    globaldir = tmp_path / "globallooks"
    globaldir.mkdir()
    (globaldir / "mystyle.json").write_text(json.dumps(sample_analysis), encoding="utf-8")
    monkeypatch.chdir(tmp_path)  # cwd 无 looks/
    monkeypatch.setattr(config, "looks_dir", lambda: globaldir)
    assert cli._resolve_template("mystyle") == globaldir / "mystyle.json"


def test_cmd_preview_writes_image(tmp_path, sample_analysis, monkeypatch):
    import json
    from PIL import Image
    from looklift import cli
    monkeypatch.chdir(tmp_path)
    t = tmp_path / "look.json"
    t.write_text(json.dumps(sample_analysis), encoding="utf-8")
    photo = tmp_path / "in.jpg"
    Image.new("RGB", (32, 32), (100, 100, 100)).save(photo)
    rc = cli.main(["preview", str(t), str(photo), "-o", str(tmp_path / "out.jpg")])
    assert rc == 0 and (tmp_path / "out.jpg").exists()


def test_cmd_export_lut(tmp_path, sample_analysis, monkeypatch):
    import json
    from looklift import cli
    monkeypatch.chdir(tmp_path)
    t = tmp_path / "look.json"
    t.write_text(json.dumps(sample_analysis), encoding="utf-8")
    rc = cli.main(["export-lut", str(t), "-o", str(tmp_path / "o.cube"), "--size", "9"])
    assert rc == 0 and (tmp_path / "o.cube").read_text(encoding="ascii").startswith("TITLE")
