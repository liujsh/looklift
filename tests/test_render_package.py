from importlib import resources
from io import BytesIO

import looklift.render as render_pkg
from PIL import ImageCms


def test_render_is_package():
    """T1 门禁:looklift.render 必须是包,不能仍是单个 render.py 模块。"""
    assert hasattr(render_pkg, "__path__")


def test_srgb_icc_packaged_resource_valid():
    """随包 ICC 必须是可解析且可识别的标准 sRGB profile。"""
    icc = resources.files("looklift.render").joinpath(
        "data", "sRGB-IEC61966-2.1.icc"
    )
    assert icc.is_file()
    icc_bytes = icc.read_bytes()
    assert icc_bytes[36:40] == b"acsp"

    profile = ImageCms.ImageCmsProfile(BytesIO(icc_bytes))
    assert "srgb" in profile.profile.profile_description.casefold()
