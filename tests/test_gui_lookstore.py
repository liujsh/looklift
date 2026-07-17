"""lookstore.save 的原子性 fold-in 修复：局部写入不留孤儿文件。

背景（v0.4 收尾 fold-in）：`save` 原实现先落 `<name>.json`，再调
`xmp_writer.analysis_to_crs`/`write_preset` 生成预设——如果 `analysis` 里混进
非数值（如 `basic.exposure = "x"`），`xmp_writer` 在 json 已经落盘之后才抛
`ValueError`，导致目录里永久留下一个只有 `.json` 没有 `.xmp` 的孤儿条目：
`lookstore.exists()` 只看 `.json` 是否存在，这个名字从此被"占用"，重试
（哪怕带上修正后的合法 analysis）也会被 `POST /api/looks` 的 409 重名检查
挡住，用户没有任何办法通过原名字重新收藏。

修复：`xmp_writer.analysis_to_crs(analysis)` 提前到任何落盘动作之前调用，
非法值在这一步就报错、两个文件都还没写；json 和 xmp 的落盘顺序不再重要，
因为走到落盘那一步时 crs 已经确认能算出来。
"""
from __future__ import annotations

import copy

import pytest

from looklift.gui import lookstore


def test_save_invalid_analysis_raises_and_leaves_no_orphan_files(tmp_path, sample_analysis):
    looks_dir = tmp_path / "looks"
    broken = copy.deepcopy(sample_analysis)
    broken["basic"]["exposure"] = "x"  # 非数值：xmp_writer._signed 在此报错

    with pytest.raises(ValueError):
        lookstore.save(looks_dir, "broken", broken)

    assert not lookstore.json_path(looks_dir, "broken").exists()
    assert not lookstore.xmp_path(looks_dir, "broken").exists()
    assert not lookstore.exists(looks_dir, "broken")


def test_save_retry_after_failed_save_succeeds_with_same_name(tmp_path, sample_analysis):
    looks_dir = tmp_path / "looks"
    broken = copy.deepcopy(sample_analysis)
    broken["basic"]["exposure"] = "x"

    with pytest.raises(ValueError):
        lookstore.save(looks_dir, "retry-me", broken)

    # 名字没有被"占用"，用修正后的合法 analysis 重试同一个名字必须成功。
    lookstore.save(looks_dir, "retry-me", sample_analysis)

    assert lookstore.json_path(looks_dir, "retry-me").is_file()
    assert lookstore.xmp_path(looks_dir, "retry-me").is_file()
    assert lookstore.load(looks_dir, "retry-me") == sample_analysis
