from pathlib import Path

import pytest
from PIL import Image

from looklift.automation_render import render_automation_jpeg


def test_render_automation_jpeg_creates_new_file_without_overwrite(tmp_path, sample_analysis):
    source = tmp_path / "source.png"
    output = tmp_path / "output.jpg"
    Image.new("RGB", (24, 16), (120, 80, 40)).save(source)

    render_automation_jpeg(source, output, sample_analysis, 0.8, 90)

    with Image.open(output) as rendered:
        assert rendered.format == "JPEG"
        assert rendered.size == (24, 16)
    original = output.read_bytes()
    with pytest.raises(FileExistsError, match="已存在"):
        render_automation_jpeg(source, output, sample_analysis, 0.8, 90)
    assert output.read_bytes() == original
    assert list(Path(tmp_path).glob(".*.tmp")) == []
