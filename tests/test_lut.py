import numpy as np
from looklift import lut


def _parse_cube(path):
    size, data = None, []
    for line in path.read_text(encoding="ascii").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("TITLE"):
            continue
        if line.startswith("LUT_3D_SIZE"):
            size = int(line.split()[1])
            continue
        if line.startswith("DOMAIN_"):
            continue
        data.append([float(x) for x in line.split()])
    return size, np.array(data)


def test_cube_format_valid(sample_analysis, tmp_path):
    out = lut.export_cube(sample_analysis, tmp_path / "t.cube", size=17)
    size, data = _parse_cube(out)
    assert size == 17
    assert data.shape == (17 ** 3, 3)          # size³ 行、每行 RGB
    assert data.min() >= 0.0 and data.max() <= 1.0


def test_identity_analysis_gives_identity_lut(sample_analysis, tmp_path):
    import copy
    a = copy.deepcopy(sample_analysis)
    a["basic"] = {k: 0 for k in a["basic"]}
    a["tone_curve"] = []
    a["hsl"] = []
    for z in ("shadows", "midtones", "highlights", "global_"):
        a["color_grading"][z] = {"hue": 0, "saturation": 0, "luminance": 0}
    a["effects"] = {"vignette_amount": 0, "grain_amount": 0}
    _, data = _parse_cube(lut.export_cube(a, tmp_path / "i.cube", size=9))
    # 第一行应是 (0,0,0),最后一行 (1,1,1);R 变化最快(Resolve 约定)
    assert np.allclose(data[0], [0, 0, 0], atol=0.01)
    assert np.allclose(data[-1], [1, 1, 1], atol=0.01)
    assert data[1][0] > data[0][0] and abs(data[1][1] - data[0][1]) < 0.01
