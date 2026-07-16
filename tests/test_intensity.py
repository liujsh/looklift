import copy

from looklift import intensity


def _lo_hi(orig):
    return sorted((0, orig))


def test_factor_1_identical_to_input_and_does_not_mutate(sample_analysis):
    original = copy.deepcopy(sample_analysis)

    result = intensity.scale_analysis(sample_analysis, 1.0)

    assert sample_analysis == original  # 入参未被修改
    assert result == original


def test_factor_0_zeroes_offsets_and_flattens_curve(sample_analysis):
    result = intensity.scale_analysis(sample_analysis, 0.0)

    assert all(v == 0 for v in result["basic"].values())

    for entry in result["hsl"]:
        assert entry["hue"] == 0
        assert entry["saturation"] == 0
        assert entry["luminance"] == 0

    cg = result["color_grading"]
    cg_orig = sample_analysis["color_grading"]
    for zone in ("shadows", "midtones", "highlights", "global_"):
        assert cg[zone]["saturation"] == 0
        assert cg[zone]["luminance"] == 0
        assert cg[zone]["hue"] == cg_orig[zone]["hue"]  # 不缩放
    assert cg["balance"] == 0
    assert cg["blending"] == cg_orig["blending"]  # 不缩放

    assert result["effects"]["vignette_amount"] == 0
    assert result["effects"]["grain_amount"] == 0

    for point in result["tone_curve"]:
        assert point["output"] == point["input"]  # 退化为对角线

    assert result["summary"] == sample_analysis["summary"]
    assert result["steps"] == sample_analysis["steps"]


def test_factor_half_scales_monotonically_between_zero_and_original(sample_analysis):
    result = intensity.scale_analysis(sample_analysis, 0.5)

    for key, orig in sample_analysis["basic"].items():
        scaled = result["basic"][key]
        if orig == 0:
            assert scaled == 0
        else:
            lo, hi = _lo_hi(orig)
            assert lo < scaled < hi

    for orig_entry, scaled_entry in zip(sample_analysis["hsl"], result["hsl"]):
        assert scaled_entry["color"] == orig_entry["color"]
        for key in ("hue", "saturation", "luminance"):
            orig = orig_entry[key]
            scaled = scaled_entry[key]
            if orig == 0:
                assert scaled == 0
            else:
                lo, hi = _lo_hi(orig)
                assert lo < scaled < hi

    cg_orig = sample_analysis["color_grading"]
    cg = result["color_grading"]
    for zone in ("shadows", "midtones", "highlights", "global_"):
        assert cg[zone]["hue"] == cg_orig[zone]["hue"]  # 不缩放
        for key in ("saturation", "luminance"):
            orig = cg_orig[zone][key]
            scaled = cg[zone][key]
            if orig == 0:
                assert scaled == 0
            else:
                lo, hi = _lo_hi(orig)
                assert lo < scaled < hi
    assert cg["blending"] == cg_orig["blending"]  # 不缩放
    lo, hi = _lo_hi(cg_orig["balance"])
    assert lo < cg["balance"] < hi

    for key in ("vignette_amount", "grain_amount"):
        orig = sample_analysis["effects"][key]
        scaled = result["effects"][key]
        lo, hi = _lo_hi(orig)
        assert lo < scaled < hi

    for orig_point, scaled_point in zip(sample_analysis["tone_curve"], result["tone_curve"]):
        assert scaled_point["input"] == orig_point["input"]
        if orig_point["output"] == orig_point["input"]:
            assert scaled_point["output"] == orig_point["output"]
        else:
            lo, hi = sorted((orig_point["input"], orig_point["output"]))
            assert lo < scaled_point["output"] < hi


def test_factor_out_of_range_is_clamped(sample_analysis):
    too_high = intensity.scale_analysis(sample_analysis, 5.0)
    too_low = intensity.scale_analysis(sample_analysis, -3.0)

    assert too_high == intensity.scale_analysis(sample_analysis, 1.0)
    assert too_low == intensity.scale_analysis(sample_analysis, 0.0)


def test_handles_sparse_input_without_keyerror():
    sparse = {"basic": {"exposure": 10}, "summary": "x"}

    result = intensity.scale_analysis(sparse, 0.5)

    assert result["basic"]["exposure"] == 5
    assert result["tone_curve"] == []
    assert result["summary"] == "x"


def test_handles_empty_input_without_keyerror():
    result = intensity.scale_analysis({}, 0.5)

    assert result == {"tone_curve": []}
