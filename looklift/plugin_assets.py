"""插件导出成片的匿名引用、冻结与单次调用暂存。"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import shutil
from dataclasses import asdict, dataclass
from pathlib import Path


class AssetBrokerError(ValueError):
    """素材引用、项目范围或暂存操作无效。"""


@dataclass(frozen=True)
class PluginAssetRef:
    asset_id: str
    project_id: str
    version_id: str
    content_hash: str
    media_type: str
    order: int

    def public_dict(self) -> dict[str, object]:
        return {
            "asset_id": self.asset_id,
            "version_id": self.version_id,
            "content_hash": self.content_hash,
            "media_type": self.media_type,
            "order": self.order,
        }


class PluginAssetBroker:
    """只接收内存中的已导出成片，不接受模型或插件提交文件路径。"""

    def __init__(self, root: Path) -> None:
        self._root = Path(root).resolve()
        self._content_root = self._root / "content"
        self._staging_root = self._root / "staging"
        self._index_path = self._root / "assets.json"
        self._content_root.mkdir(parents=True, exist_ok=True)
        self._staging_root.mkdir(parents=True, exist_ok=True)
        self._items: dict[str, PluginAssetRef] = {}
        self._load()

    def freeze(
        self,
        *,
        project_id: str,
        version_ids: tuple[str, ...],
        contents: tuple[bytes, ...],
        media_type: str,
    ) -> tuple[PluginAssetRef, ...]:
        if not project_id or len(version_ids) != len(contents) or not contents:
            raise AssetBrokerError("素材集合与正式版本不一致")
        if media_type not in {"image/jpeg", "image/png", "image/tiff"}:
            raise AssetBrokerError("导出素材类型不受支持")
        refs: list[PluginAssetRef] = []
        for order, (version_id, content) in enumerate(zip(version_ids, contents, strict=True)):
            if not isinstance(content, bytes) or not content or not isinstance(version_id, str) or not version_id:
                raise AssetBrokerError("导出素材内容无效")
            digest = hashlib.sha256(content).hexdigest()
            asset_id = secrets.token_hex(16)
            path = self._content_root / asset_id
            temporary = path.with_suffix(".tmp")
            temporary.write_bytes(content)
            os.replace(temporary, path)
            ref = PluginAssetRef(asset_id, project_id, version_id, digest, media_type, order)
            self._items[asset_id] = ref
            refs.append(ref)
        self._save()
        return tuple(refs)

    def get(self, asset_id: str) -> PluginAssetRef:
        try:
            return self._items[_safe_id(asset_id, "素材")]
        except KeyError as exc:
            raise AssetBrokerError("未知素材引用") from exc

    def stage(
        self,
        *,
        project_id: str,
        action_id: str,
        asset_ids: tuple[str, ...],
    ) -> tuple[Path, ...]:
        safe_action = _safe_id(action_id, "Action")
        if not asset_ids:
            raise AssetBrokerError("暂存素材不能为空")
        refs = tuple(self.get(asset_id) for asset_id in asset_ids)
        if any(ref.project_id != project_id for ref in refs):
            raise AssetBrokerError("素材不属于当前项目")
        target = (self._staging_root / safe_action).resolve()
        if target.parent != self._staging_root:
            raise AssetBrokerError("Action 暂存路径无效")
        target.mkdir(exist_ok=False)
        staged: list[Path] = []
        suffixes = {"image/jpeg": ".jpg", "image/png": ".png", "image/tiff": ".tif"}
        try:
            for order, ref in enumerate(refs, start=1):
                source = self._content_root / ref.asset_id
                if hashlib.sha256(source.read_bytes()).hexdigest() != ref.content_hash:
                    raise AssetBrokerError("冻结素材内容摘要不一致")
                destination = target / f"asset-{order}{suffixes[ref.media_type]}"
                shutil.copyfile(source, destination)
                staged.append(destination)
        except Exception:
            shutil.rmtree(target, ignore_errors=True)
            raise
        return tuple(staged)

    def revoke_action(self, action_id: str) -> None:
        safe_action = _safe_id(action_id, "Action")
        target = (self._staging_root / safe_action).resolve()
        if target.parent != self._staging_root:
            raise AssetBrokerError("Action 暂存路径无效")
        if target.exists():
            shutil.rmtree(target)

    def _save(self) -> None:
        payload = [asdict(self._items[key]) for key in sorted(self._items)]
        temporary = self._index_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        os.replace(temporary, self._index_path)

    def _load(self) -> None:
        if not self._index_path.exists():
            return
        try:
            payload = json.loads(self._index_path.read_text(encoding="utf-8"))
            for raw in payload:
                ref = PluginAssetRef(**raw)
                _safe_id(ref.asset_id, "素材")
                self._items[ref.asset_id] = ref
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise AssetBrokerError("素材索引损坏") from exc


def _safe_id(value: str, label: str) -> str:
    if not isinstance(value, str) or len(value) != 32 or not value.isascii() or not value.isalnum():
        raise AssetBrokerError(f"{label} ID 不安全或素材引用无效")
    return value
