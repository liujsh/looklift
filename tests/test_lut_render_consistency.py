import numpy as np

from looklift import lut
from looklift.render import pipeline


def _analysis():
    return {
        "basic": {
            "temperature_shift": 30,
            "tint_shift": 0,
            "exposure": 0.6,
            "contrast": 20,
            "highlights": 0,
            "shadows": 0,
            "whites": 0,
            "blacks": 0,
            "texture": 0,
            "clarity": 0,
            "dehaze": 0,
            "vibrance": 0,
            "saturation": 10,
        },
        "tone_curve": [],
        "hsl": [],
        "color_grading": {},
        "effects": {},
    }


def _cube_lookup(path, rgb):
    lines = [line.strip() for line in path.read_text(encoding="ascii").splitlines()]
    size = int(
        next(line.split()[1] for line in lines if line.startswith("LUT_3D_SIZE"))
    )
    rows = [
        line
        for line in lines
        if line
        and not line.startswith(("#", "TITLE", "LUT_3D_SIZE", "DOMAIN_"))
    ]
    table = np.asarray([[float(value) for value in row.split()] for row in rows])
    table = table.reshape(size, size, size, 3)
    position = np.clip(np.asarray(rgb, np.float32), 0, 1) * (size - 1)
    low = np.floor(position).astype(int)
    high = np.minimum(low + 1, size - 1)
    fraction = position - low
    output = np.zeros(3, dtype=np.float32)
    for db in (0, 1):
        for dg in (0, 1):
            for dr in (0, 1):
                index = (
                    high[2] if db else low[2],
                    high[1] if dg else low[1],
                    high[0] if dr else low[0],
                )
                weight = (
                    (fraction[2] if db else 1 - fraction[2])
                    * (fraction[1] if dg else 1 - fraction[1])
                    * (fraction[0] if dr else 1 - fraction[0])
                )
                output += weight * table[index]
    return output


def test_cube_matches_render_color_subset_at_sample_points(tmp_path):
    analysis = _analysis()
    cube = lut.export_cube(analysis, tmp_path / "consistent.cube", size=33)
    for rgb in ([0.25, 0.25, 0.25], [0.5, 0.4, 0.3], [0.8, 0.2, 0.2]):
        source = np.asarray(rgb, dtype=np.float32).reshape(1, 1, 3)
        expected = pipeline.render_arr(source, analysis)[0, 0]
        actual = _cube_lookup(cube, rgb)
        np.testing.assert_allclose(actual, expected, atol=2.0 / 255)


def test_lut_ignores_spatial_detail_and_output_effects(tmp_path):
    baseline = _analysis()
    spatial = _analysis()
    spatial["basic"].update({"texture": 80, "clarity": 70, "dehaze": 60})
    spatial["effects"] = {"vignette_amount": -70, "grain_amount": 80}
    first = lut.export_cube(baseline, tmp_path / "base.cube", size=9)
    second = lut.export_cube(spatial, tmp_path / "spatial.cube", size=9)
    assert first.read_bytes() == second.read_bytes()
