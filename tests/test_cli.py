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


def test_refine_auto_requires_source(tmp_path, sample_analysis, monkeypatch):
    import json
    from looklift import cli
    monkeypatch.chdir(tmp_path)
    t = tmp_path / "look.json"
    t.write_text(json.dumps(sample_analysis), encoding="utf-8")
    rc = cli.main(["refine", str(t), "--target", "x.jpg", "--auto"])
    assert rc == 1


def test_refine_manual_requires_attempt(tmp_path, sample_analysis, monkeypatch):
    """--auto 未指定时走手动模式;缺 --attempt 应报错退出,不去动 target 文件。"""
    import json
    from looklift import cli
    monkeypatch.chdir(tmp_path)
    t = tmp_path / "look.json"
    t.write_text(json.dumps(sample_analysis), encoding="utf-8")
    rc = cli.main(["refine", str(t), "--target", "x.jpg"])
    assert rc == 1


def test_refine_auto_end_to_end(tmp_path, sample_analysis, monkeypatch, capsys):
    """--auto 接入 autorefine 闭环:AI 与评分全部 monkeypatch,验证共享的备份/写模版逻辑仍会跑。"""
    import copy
    import json
    from PIL import Image
    from looklift import autorefine, cli
    monkeypatch.chdir(tmp_path)
    template = tmp_path / "look.json"
    template.write_text(json.dumps(sample_analysis), encoding="utf-8")
    src = tmp_path / "src.jpg"; tgt = tmp_path / "tgt.jpg"
    Image.new("RGB", (16, 16), (90, 90, 90)).save(src)
    Image.new("RGB", (16, 16), (140, 140, 140)).save(tgt)

    scores = iter([50.0, 90.0, 90.2])  # 第 2 轮起提升 < 默认 min_gain(1.0),提前收敛
    monkeypatch.setattr(autorefine.render, "score", lambda rendered, target_img: next(scores))
    monkeypatch.setattr(autorefine.analyzer, "refine",
                        lambda current, attempt, target, backend="auto": copy.deepcopy(current))
    # cmd_refine 打印进度横幅前会调 analyzer.resolve_backend() 探测后端;
    # CI 机器上既无 claude CLI 也无 ANTHROPIC_API_KEY,不 mock 会导致 RuntimeError。
    monkeypatch.setattr(cli.analyzer, "resolve_backend", lambda b="auto": "cli")

    rc = cli.main(["refine", str(template), "--target", str(tgt), "--source", str(src), "--auto", "3"])
    assert rc == 0
    assert (tmp_path / "look.json.bak").exists()  # 共享的备份逻辑生效
    out = capsys.readouterr().out
    assert "自动校准" in out and "评分曲线" in out


def test_gui_help_shows_browser_and_port(capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(["gui", "--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "--browser" in out
    assert "--port" in out
