import xml.dom.minidom

from looklift import xmp_reader, xmp_writer


def test_analysis_to_crs_mapping(sample_analysis):
    crs = xmp_writer.analysis_to_crs(sample_analysis)
    assert crs["Exposure2012"] == "+0.35"
    assert crs["Highlights2012"] == "-40"
    assert crs["Dehaze"] == "0"  # 零值不带符号
    assert crs["HueAdjustmentBlue"] == "-15"
    assert crs["SaturationAdjustmentOrange"] == "-10"
    assert crs["SplitToningShadowHue"] == "210"
    assert crs["ColorGradeMidtoneSat"] == "0"
    assert crs["ToneCurveName2012"] == "Custom"
    assert crs["ToneCurvePV2012"] == ["0, 18", "64, 60", "192, 200", "255, 245"]
    assert crs["PostCropVignetteAmount"] == "-12"
    assert crs["GrainAmount"] == "20"


def test_preset_is_valid_xml_and_roundtrips(sample_analysis, tmp_path):
    crs = xmp_writer.analysis_to_crs(sample_analysis)
    out = xmp_writer.write_preset(crs, "Test Look", tmp_path / "t.xmp")
    xml.dom.minidom.parse(str(out))  # 不抛异常即合法

    settings = xmp_reader.read_crs_settings(out)
    assert settings["Exposure2012"] == "+0.35"
    assert settings["ToneCurvePV2012"] == ["0, 18", "64, 60", "192, 200", "255, 245"]
    assert settings["PresetType"] == "Normal"


def test_sidecar_named_after_raw(sample_analysis, tmp_path):
    crs = xmp_writer.analysis_to_crs(sample_analysis)
    raw = tmp_path / "IMG_0001.CR3"
    raw.write_bytes(b"\x00fake")
    out = xmp_writer.write_sidecar(crs, raw)
    assert out == tmp_path / "IMG_0001.xmp"
    settings = xmp_reader.read_crs_settings(out)
    assert "PresetType" not in settings  # sidecar 不是预设
    assert settings["HasSettings"] == "True"


def test_preset_name_escaped(sample_analysis, tmp_path):
    crs = xmp_writer.analysis_to_crs(sample_analysis)
    out = xmp_writer.write_preset(crs, 'A<B>&"C', tmp_path / "esc.xmp")
    xml.dom.minidom.parse(str(out))
