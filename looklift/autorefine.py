"""refine 自动闭环:渲染 → 评分 → AI 修正 → 再渲染,直到收敛或到轮数上限。"""
from __future__ import annotations

import copy
import shutil
import tempfile
from pathlib import Path

from PIL import Image

from . import analyzer, render


def auto_refine(
    analysis: dict,
    source: str | Path,
    target: str | Path,
    rounds: int = 3,
    min_gain: float = 1.0,
    backend: str = "auto",
    on_round=None,
) -> tuple[dict, list[float]]:
    """返回 (最佳参数, 评分历史)。history[0] 是初始参数的评分,之后每轮一项。

    每轮:用当前参数渲染 → 评分 → 交给 AI 对比效果图与目标图修正参数。收敛判定在
    评分历史追加新一轮之后,比较最近两轮之差是否小于 min_gain;最佳参数取全程
    评分最高的一版(不一定是最后一版,AI 修正可能变差)。
    """
    current = copy.deepcopy(analysis)

    # Windows 上 tempfile.mkstemp() 返回的 fd 处于打开状态,PIL 再次以路径打开写入
    # 容易撞上文件占用;改用一次性 mkdtemp + 按轮编号命名,规避该问题,且清理只需
    # 结束时整目录删除一次,不会跨轮累积。source/target 同样显式 close(避免持有
    # 用户原片/目标图的文件句柄直到进程退出才释放)。
    tmp_dir = Path(tempfile.mkdtemp(prefix="looklift-refine-"))
    try:
        with Image.open(source) as src, Image.open(target) as tgt:
            def evaluate(params: dict, i: int) -> tuple[float, Path]:
                rendered = render.render(src, params)
                attempt_path = tmp_dir / f"attempt_{i}.jpg"
                rendered.save(
                    attempt_path,
                    quality=92,
                    icc_profile=rendered.info["icc_profile"],
                )
                return render.score(rendered, tgt), attempt_path

            s, attempt = evaluate(current, 0)
            history = [s]
            best, best_score = current, s
            if on_round:
                on_round(0, s)

            for i in range(1, rounds + 1):
                current = analyzer.refine(current, attempt, target, backend=backend)
                s, attempt = evaluate(current, i)
                history.append(s)
                if on_round:
                    on_round(i, s)
                if s > best_score:
                    best, best_score = current, s
                if s - history[-2] < min_gain:
                    break
            return best, history
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
