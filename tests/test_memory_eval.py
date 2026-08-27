from looklift.context_memory import ContextEntry
from looklift.memory_eval import RecallCase, evaluate_recall, memory_token_ratio
from looklift.memory_retrieval import RetrievedMemory


def result(entry_id, content):
    entry = ContextEntry(entry_id, "preference", content, "auto", state="active")
    return RetrievedMemory(entry, 1, ("bm25",), 1.0, "bm25")


def test_evaluate_recall_reports_hits_noise_and_forbidden():
    metrics = evaluate_recall(
        [RecallCase("c1", frozenset({"good"}), frozenset({"bad"}))],
        {"c1": [result("good", "相关"), result("bad", "无关") ]},
        k=2,
    )
    assert metrics.recall_at_k == 1.0
    assert metrics.precision_at_k == 0.5
    assert metrics.noise_rate == 0.5
    assert metrics.forbidden_rate == 1.0


def test_empty_cases_and_token_ratio_are_deterministic():
    assert evaluate_recall([], {}).recall_at_k == 0.0
    assert memory_token_ratio("abcd", "abcdefghijkl") == 1 / 3
