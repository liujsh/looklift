import copy

from PIL import Image

from looklift import autorefine


def test_auto_refine_keeps_best_and_stops_on_convergence(tmp_path, sample_analysis, monkeypatch):
    src = tmp_path / "src.jpg"; tgt = tmp_path / "tgt.jpg"
    Image.new("RGB", (32, 32), (90, 90, 90)).save(src)
    Image.new("RGB", (32, 32), (140, 140, 140)).save(tgt)

    scores = iter([50.0, 70.0, 70.5, 70.6])  # 第 3 轮起提升 < min_gain
    monkeypatch.setattr(autorefine.render, "score", lambda r, t: next(scores))

    calls = {"n": 0}
    def fake_refine(current, attempt, target, backend="auto"):
        calls["n"] += 1
        out = copy.deepcopy(current)
        out["basic"]["exposure"] = calls["n"] * 0.1
        return out
    monkeypatch.setattr(autorefine.analyzer, "refine", fake_refine)

    best, history = autorefine.auto_refine(
        sample_analysis, src, tgt, rounds=5, min_gain=1.0)
    assert history == [50.0, 70.0, 70.5]      # 第 3 轮提升 0.5 < 1.0,停
    assert best["basic"]["exposure"] == 0.2   # 评分最高(70.5)那版参数
    assert calls["n"] == 2                    # 收敛后不再调 AI


def test_auto_refine_respects_rounds_limit(tmp_path, sample_analysis, monkeypatch):
    src = tmp_path / "s.jpg"; tgt = tmp_path / "t.jpg"
    Image.new("RGB", (16, 16)).save(src); Image.new("RGB", (16, 16)).save(tgt)
    it = iter([10.0, 20.0, 30.0, 40.0, 50.0, 60.0])
    monkeypatch.setattr(autorefine.render, "score", lambda r, t: next(it))
    monkeypatch.setattr(autorefine.analyzer, "refine",
                        lambda c, a, t, backend="auto": copy.deepcopy(c))
    best, history = autorefine.auto_refine(sample_analysis, src, tgt, rounds=3, min_gain=1.0)
    assert len(history) == 4  # 初始评分 + 3 轮


def test_auto_refine_fires_on_round_for_every_round(tmp_path, sample_analysis, monkeypatch):
    """on_round(i, score) 应在第 0 轮(初始评分)和之后每一轮都触发一次。"""
    src = tmp_path / "s.jpg"; tgt = tmp_path / "t.jpg"
    Image.new("RGB", (16, 16)).save(src); Image.new("RGB", (16, 16)).save(tgt)
    scores = iter([10.0, 20.0, 30.0])
    monkeypatch.setattr(autorefine.render, "score", lambda r, t: next(scores))
    monkeypatch.setattr(autorefine.analyzer, "refine",
                        lambda c, a, t, backend="auto": copy.deepcopy(c))

    seen = []
    autorefine.auto_refine(
        sample_analysis, src, tgt, rounds=2, min_gain=1.0,
        on_round=lambda i, s: seen.append((i, s)))
    assert seen == [(0, 10.0), (1, 20.0), (2, 30.0)]
