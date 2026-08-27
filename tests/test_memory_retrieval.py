from looklift.context_memory import ContextEntry
from looklift.memory_retrieval import HybridMemoryRetriever, RecallQuery


def entry(entry_id, content, *, scope="global", project_id=None, entry_type="preference", description=""):
    return ContextEntry(entry_id, entry_type, content, "auto", state="active", scope=scope, project_id=project_id, description=description)


def test_bm25_retrieves_relevant_chinese_memory_and_excludes_other_project():
    items = [
        entry("cool", "室内人像偏好冷色调和自然肤色"),
        entry("landscape", "风景照偏好高饱和绿色"),
        entry("other", "本项目客户要求暖色", scope="project", project_id="p2"),
    ]
    result = HybridMemoryRetriever().retrieve(items, RecallQuery("室内人像自然肤色", project_id="p1"))
    assert result[0].entry.entry_id == "cool"
    assert "other" not in [item.entry.entry_id for item in result]


def test_vector_and_bm25_are_fused_with_stable_sources():
    items = [entry("a", "冷色肤色"), entry("b", "暖色肤色")]
    vectors = {"a": [1.0, 0.0], "b": [0.0, 1.0]}
    result = HybridMemoryRetriever().retrieve(items, RecallQuery("自然肤色"), embed_query=lambda _: [1.0, 0.0], embeddings=vectors)
    assert result[0].entry.entry_id == "a"
    assert "vector" in result[0].sources


def test_budget_and_conflict_group_limit():
    items = [entry("a", "低饱和", description="#group:tone"), entry("b", "高饱和", description="#group:tone"), entry("c", "自然肤色")]
    result = HybridMemoryRetriever().retrieve(items, RecallQuery("低饱和 自然肤色", token_budget=3))
    assert len(result) <= 2
    assert sum("#group:tone" in item.entry.description for item in result) <= 1


def test_rule_artifact_filter_and_expired_entry():
    items = [
        entry("rule-photo", "规则", entry_type="rule", description="#artifact:photo"),
        entry("rule-web", "规则", entry_type="rule", description="#artifact:web"),
    ]
    result = HybridMemoryRetriever().retrieve(items, RecallQuery("规则", artifact_type="photo"))
    assert [item.entry.entry_id for item in result] == ["rule-photo"]
