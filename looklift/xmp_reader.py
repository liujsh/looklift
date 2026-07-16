"""从 JPEG 中提取嵌入的 XMP 元数据(Lightroom / Camera Raw 调整参数)。

Lightroom 导出时如果勾选了"包含元数据",crs:* 命名空间的全部调整参数
会以 XMP packet 的形式嵌在 JPEG 的 APP1 段里。这里直接在字节流中定位
<x:xmpmeta ...> ... </x:xmpmeta>,无需完整解析 JPEG 结构。
"""

from __future__ import annotations

import re
from pathlib import Path

CRS_NS = "http://ns.adobe.com/camera-raw-settings/1.0/"

# crs 参数既可能是 rdf:Description 的 XML 属性(常见),也可能是子元素
_ATTR_RE = re.compile(r'crs:([A-Za-z0-9_]+)="([^"]*)"')
_ELEM_RE = re.compile(r"<crs:([A-Za-z0-9_]+)>(.*?)</crs:\1>", re.DOTALL)
_SEQ_LI_RE = re.compile(r"<rdf:li>(.*?)</rdf:li>", re.DOTALL)


def extract_xmp_packet(path: str | Path) -> str | None:
    """返回文件中嵌入的第一个 XMP packet 文本,没有则返回 None。"""
    data = Path(path).read_bytes()
    start = data.find(b"<x:xmpmeta")
    if start == -1:
        return None
    end = data.find(b"</x:xmpmeta>", start)
    if end == -1:
        return None
    return data[start : end + len(b"</x:xmpmeta>")].decode("utf-8", errors="replace")


def read_crs_settings(path: str | Path) -> dict[str, object] | None:
    """读取照片中嵌入的全部 crs(Camera Raw)参数。

    返回 {参数名: 值} 字典;值为字符串,rdf:Seq 列表(如曲线点)为字符串列表。
    照片没有嵌入 XMP、或 XMP 中没有 crs 参数时返回 None。
    """
    xmp = extract_xmp_packet(path)
    if xmp is None:
        return None

    settings: dict[str, object] = {}
    for name, value in _ATTR_RE.findall(xmp):
        settings[name] = value
    for name, body in _ELEM_RE.findall(xmp):
        items = _SEQ_LI_RE.findall(body)
        if items:
            settings[name] = [i.strip() for i in items]
        else:
            settings[name] = body.strip()

    return settings or None
