from looklift import xmp_reader

XMP_SAMPLE = """<x:xmpmeta xmlns:x="adobe:ns:meta/">
 <rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
  <rdf:Description rdf:about=""
    xmlns:crs="http://ns.adobe.com/camera-raw-settings/1.0/"
    crs:Exposure2012="+0.50"
    crs:Contrast2012="-20">
   <crs:ToneCurvePV2012>
    <rdf:Seq>
     <rdf:li>0, 0</rdf:li>
     <rdf:li>255, 255</rdf:li>
    </rdf:Seq>
   </crs:ToneCurvePV2012>
  </rdf:Description>
 </rdf:RDF>
</x:xmpmeta>"""


def test_reads_attrs_and_seq_elements(tmp_path):
    f = tmp_path / "photo.jpg"
    # 模拟嵌在 JPEG 字节流中间的 XMP packet
    f.write_bytes(b"\xff\xd8\xff\xe1" + XMP_SAMPLE.encode() + b"\xff\xd9")
    s = xmp_reader.read_crs_settings(f)
    assert s["Exposure2012"] == "+0.50"
    assert s["Contrast2012"] == "-20"
    assert s["ToneCurvePV2012"] == ["0, 0", "255, 255"]


def test_no_xmp_returns_none(tmp_path):
    f = tmp_path / "plain.jpg"
    f.write_bytes(b"\xff\xd8\xff\xdb no xmp here \xff\xd9")
    assert xmp_reader.read_crs_settings(f) is None
