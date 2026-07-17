from copy import deepcopy

import pytest

from looklift.analyzer import ANALYSIS_SCHEMA, _COLOR_KEYS
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


def test_tone_curve_has_bounds_but_is_not_adjustable_path():
    point = ANALYSIS_SCHEMA["properties"]["tone_curve"]["items"]["properties"]
    assert (point["input"]["minimum"], point["input"]["maximum"]) == (0, 255)
    assert (point["output"]["minimum"], point["output"]["maximum"]) == (0, 255)
    assert not any(path.startswith("tone_curve") for path in contract.param_paths())


def test_param_paths_exactly_cover_adjustable_schema_numeric_leaves():
    properties = ANALYSIS_SCHEMA["properties"]
    expected = {
        *(f"basic.{field}" for field, node in properties["basic"]["properties"].items()
          if node.get("type") == "number"),
        *(f"hsl.{color}.{field}" for color in _COLOR_KEYS
          for field, node in properties["hsl"]["items"]["properties"].items()
          if node.get("type") == "number"),
        *(f"color_grading.{('global' if zone == 'global_' else zone)}.{field}"
          for zone, node in properties["color_grading"]["properties"].items()
          if node.get("type") == "object"
          for field, leaf in node["properties"].items()
          if leaf.get("type") == "number"),
        *(f"color_grading.{field}"
          for field, node in properties["color_grading"]["properties"].items()
          if node.get("type") == "number"),
        *(f"effects.{field}" for field, node in properties["effects"]["properties"].items()
          if node.get("type") == "number"),
    }
    paths = contract.param_paths()
    assert set(paths) == expected
    assert len(paths) == len(expected)


@pytest.mark.parametrize(
    "path",
    [
        "unknown.value",
        "hsl.cyan.hue",
        "basic.unknown",
        "hsl.blue.unknown",
        "color_grading.shadows.unknown",
        "effects.unknown",
        "basic",
        "basic.exposure.extra",
        "hsl.blue",
        "hsl.blue.hue.extra",
        "color_grading.shadows",
        "color_grading.blending.extra",
    ],
)
def test_invalid_paths_raise_key_error_without_mutating_analysis(sample_analysis, path):
    before = deepcopy(sample_analysis)

    with pytest.raises(KeyError) as bounds_error:
        contract.param_bounds(path)
    assert bounds_error.value.args == (path,)

    with pytest.raises(KeyError) as resolve_error:
        contract.resolve_path(sample_analysis, path)
    assert resolve_error.value.args == (path,)
    assert sample_analysis == before
