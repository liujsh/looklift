"""基于 FastEmbed/ONNX Runtime 的本地中文 Memory 向量索引。"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable, Iterable, Sequence

from .context_memory import ContextEntry


DEFAULT_EMBEDDING_MODEL = "BAAI/bge-small-zh-v1.5"


class EmbeddingUnavailable(RuntimeError):
    """本地向量模型未安装或加载失败。"""


class LocalEmbeddingIndex:
    """按 Memory 内容 Hash 增量更新的本地向量缓存。"""

    def __init__(
        self,
        root: Path,
        *,
        model_name: str = DEFAULT_EMBEDDING_MODEL,
        model_factory: Callable[[str, Path], object] | None = None,
    ) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / "embeddings.json"
        self.model_name = model_name
        self._model_factory = model_factory
        self._loaded_model: object | None = None

    def sync(self, entries: Iterable[ContextEntry]) -> dict[str, tuple[float, ...]]:
        entries = tuple(item for item in entries if item.enabled and item.state == "active")
        cache = self._load()
        cached_entries = cache.get("entries", {}) if cache.get("model") == self.model_name else {}
        missing = [
            item for item in entries
            if cached_entries.get(item.entry_id, {}).get("content_hash") != item.content_hash
        ]
        vectors = self._embed([self._searchable(item) for item in missing]) if missing else []
        current: dict[str, dict[str, object]] = {}
        for item in entries:
            cached = cached_entries.get(item.entry_id)
            if cached and cached.get("content_hash") == item.content_hash:
                current[item.entry_id] = cached
        for item, vector in zip(missing, vectors):
            current[item.entry_id] = {
                "content_hash": item.content_hash,
                "vector": list(vector),
            }
        self._write({"schema_version": 1, "model": self.model_name, "entries": current})
        return {
            entry_id: tuple(float(value) for value in payload["vector"])
            for entry_id, payload in current.items()
        }

    def embed_query(self, text: str) -> tuple[float, ...]:
        vectors = self._embed([text])
        return vectors[0] if vectors else ()

    def _embed(self, texts: Sequence[str]) -> list[tuple[float, ...]]:
        if not texts:
            return []
        model = self._model()
        try:
            raw = model.embed(list(texts))  # type: ignore[attr-defined]
            return [tuple(float(value) for value in vector) for vector in raw]
        except Exception as exc:
            raise EmbeddingUnavailable("本地 Memory 向量计算失败") from exc

    def _model(self) -> object:
        if self._loaded_model is not None:
            return self._loaded_model
        try:
            if self._model_factory is not None:
                model = self._model_factory(self.model_name, self.root / "models")
            else:
                from fastembed import TextEmbedding

                model = TextEmbedding(
                    model_name=self.model_name,
                    cache_dir=str(self.root / "models"),
                )
        except Exception as exc:
            raise EmbeddingUnavailable(
                "本地 Memory Embedding 不可用，请安装 looklift[memory]"
            ) from exc
        self._loaded_model = model
        return model

    def _load(self) -> dict:
        if not self.path.is_file():
            return {}
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write(self, payload: dict) -> None:
        temporary = self.path.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    @staticmethod
    def _searchable(entry: ContextEntry) -> str:
        return " | ".join(
            value for value in (entry.name, entry.description, entry.content, entry.evidence) if value
        )
