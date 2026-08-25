"""读取并校验随应用发布的只读 Domain Pack 来源。"""

from __future__ import annotations

import hashlib
from importlib.resources import files

from .domain_pack_types import VersionedText


_PHOTO_EDITING_ID = "looklift.photo_editing"
_PHOTO_EDITING_VERSION = 1
_PHOTO_EDITING_SHA256 = (
    "4593d2d1926c44825eb2424a5c8ab5875b8f7d4437760dc2ac605a5c650a4e00"
)


class DomainPackSourceError(RuntimeError):
    """内置领域来源缺失或与发布版本不一致。"""


def load_photo_editing_contract() -> VersionedText:
    """加载固定版本的通用修图契约，并在进入 Prompt 前校验完整性。"""
    resource = files("looklift").joinpath("data", "domain", "PHOTO_EDITING.md")
    try:
        content = resource.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        raise DomainPackSourceError("内置 PHOTO_EDITING.md 缺失") from exc

    normalized = content.replace("\r\n", "\n").replace("\r", "\n").strip()
    content_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    if content_hash != _PHOTO_EDITING_SHA256:
        raise DomainPackSourceError(
            "内置 PHOTO_EDITING.md 与声明版本不一致，请同步更新版本与摘要"
        )
    return VersionedText(
        source_id=_PHOTO_EDITING_ID,
        version=_PHOTO_EDITING_VERSION,
        content=normalized,
    )
