import subprocess
import sys
import textwrap


_BLOCK_NUMBA = """
import importlib.abc
import sys

class BlockNumba(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "numba" or fullname.startswith("numba."):
            raise ModuleNotFoundError("测试阻断 numba", name=fullname)
        return None

sys.meta_path.insert(0, BlockNumba())
"""


def _run_without_numba(body: str) -> subprocess.CompletedProcess:
    script = textwrap.dedent(_BLOCK_NUMBA + body)
    return subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_import_without_numba_selects_numpy_runtime():
    result = _run_without_numba(
        """
from looklift.render import kernel
assert kernel.HAS_NUMBA is False
"""
    )
    assert result.returncode == 0, result.stderr


def test_public_render_without_numba_outputs_brightened_image_with_icc():
    result = _run_without_numba(
        """
import numpy as np
from PIL import Image
from looklift import render

analysis = {
    "basic": {"exposure": 1.0},
    "tone_curve": [],
    "hsl": [],
    "color_grading": {},
    "effects": {},
}
source = Image.new("RGB", (8, 8), (64, 64, 64))
output = render.render(source, analysis)
assert isinstance(output, Image.Image)
assert np.asarray(output).mean() > np.asarray(source).mean()
assert output.info.get("icc_profile")
"""
    )
    assert result.returncode == 0, result.stderr
