import pytest

from looklift.render import contract


def test_param_paths_covers_domains_excludes_tone_curve():
    paths = contract.param_paths()
    assert "basic.exposure" in paths
    assert "basic.saturation" in paths
    assert "hsl.blue.saturation" in paths
    assert "color_grading.shadows.hue" in paths
    assert "color_grading.global.hue" in paths
    assert "color_grading.blending" in paths
    assert "color_grading.balance" in paths
    assert "effects.vignette_amount" in paths
    assert "effects.grain_amount" in paths
    assert not any(p.startswith("tone_curve") for p in paths)
    assert len(paths) == len(set(paths))


def test_every_path_has_numeric_bounds():
    for path in contract.param_paths():
        lo, hi = contract.param_bounds(path)
        assert lo is not None and hi is not None
        assert lo < hi


def test_bounds_read_from_schema():
    assert contract.param_bounds("basic.exposure") == (-5.0, 5.0)
    assert contract.param_bounds("basic.contrast") == (-100, 100)
    assert contract.param_bounds("effects.grain_amount") == (0, 100)
    assert contract.param_bounds("color_grading.shadows.hue") == (0, 360)


def test_resolve_path_basic_and_effects(sample_analysis):
    container, key = contract.resolve_path(sample_analysis, "basic.exposure")
    assert container[key] == sample_analysis["basic"]["exposure"]
    container, key = contract.resolve_path(sample_analysis, "effects.grain_amount")
    assert container[key] == sample_analysis["effects"]["grain_amount"]


def test_resolve_path_hsl_hits_array_item_by_color(sample_analysis):
    # sample_analysis 的 hsl 里有 blue 项
    container, key = contract.resolve_path(sample_analysis, "hsl.blue.saturation")
    assert container["color"] == "blue"
    assert key == "saturation"
    assert container[key] == 12


def test_resolve_path_hsl_inserts_missing_color_zeroed():
    analysis = {"hsl": []}
    container, key = contract.resolve_path(analysis, "hsl.green.hue")
    assert container == {"color": "green", "hue": 0, "saturation": 0, "luminance": 0}
    assert analysis["hsl"][0] is container
    assert key == "hue"


def test_resolve_path_global_maps_to_underscore_key(sample_analysis):
    container, key = contract.resolve_path(sample_analysis, "color_grading.global.hue")
    assert container is sample_analysis["color_grading"]["global_"]
    assert key == "hue"


def test_resolve_path_color_grading_blending(sample_analysis):
    container, key = contract.resolve_path(sample_analysis, "color_grading.blending")
    assert container is sample_analysis["color_grading"]
    assert key == "blending"
