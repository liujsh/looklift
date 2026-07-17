from importlib import resources

import looklift.render as render_pkg


def test_render_is_package():
    """T1 门禁:looklift.render 必须是包,不能仍是单个 render.py 模块。"""
    assert hasattr(render_pkg, "__path__")


def test_srgb_icc_packaged_resource_nonempty():
    """标准 sRGB ICC 必须作为 looklift.render 的非空包资源可读取。"""
    icc = resources.files("looklift.render").joinpath(
        "data", "sRGB-IEC61966-2.1.icc"
    )
    assert icc.is_file()
    assert len(icc.read_bytes()) > 0
