from looklift.context_memory import ContextEntry, ContextMemoryStore
from looklift.memory_embeddings import LocalEmbeddingIndex
from looklift.memory_retrieval import RecallQuery


class FakeModel:
    def __init__(self, calls):
        self.calls = calls

    def embed(self, texts):
        self.calls.append(tuple(texts))
        for text in texts:
            yield [float("冷" in text), float("暖" in text), 1.0]


def test_local_embedding_index_caches_by_content_hash(tmp_path):
    calls = []
    index = LocalEmbeddingIndex(tmp_path, model_factory=lambda _name, _cache: FakeModel(calls))
    entries = [ContextEntry("cool", "preference", "偏好冷色", "auto")]
    first = index.sync(entries)
    second = index.sync(entries)
    assert first == second
    assert len(calls) == 1

    changed = [ContextEntry("cool", "preference", "偏好暖色", "auto")]
    index.sync(changed)
    assert len(calls) == 2


def test_store_uses_local_embedding_index_for_hybrid_retrieval(tmp_path):
    store = ContextMemoryStore(tmp_path / "memory")
    store.put(ContextEntry("cool", "preference", "低温色彩", "auto"))
    store.put(ContextEntry("warm", "preference", "高温色彩", "auto"))
    calls = []
    index = LocalEmbeddingIndex(
        tmp_path / "vectors", model_factory=lambda _name, _cache: FakeModel(calls)
    )
    result = store.retrieve(RecallQuery("冷色偏好"), embedding_index=index)
    assert result[0].entry.entry_id == "cool"
    assert "vector" in result[0].sources
