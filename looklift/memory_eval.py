"""Memory 离线评测指标；仅处理固定 fixture，不调用模型或网络。"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from .memory_retrieval import RetrievedMemory


@dataclass(frozen=True)
class RecallCase:
    case_id: str
    gold_ids: frozenset[str]
    must_not_ids: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RecallMetrics:
    recall_at_k: float
    precision_at_k: float
    noise_rate: float
    forbidden_rate: float


def evaluate_recall(
    cases: Iterable[RecallCase],
    results: dict[str, Sequence[RetrievedMemory]],
    *,
    k: int = 5,
) -> RecallMetrics:
    if k <= 0:
        raise ValueError("k 必须为正数")
    cases = tuple(cases)
    if not cases:
        return RecallMetrics(0.0, 0.0, 0.0, 0.0)
    recalls: list[float] = []
    precisions: list[float] = []
    noises: list[float] = []
    forbidden: list[float] = []
    for case in cases:
        top = tuple(results.get(case.case_id, ()))[:k]
        ids = [item.entry.entry_id for item in top]
        hit = len(set(ids) & case.gold_ids)
        recalls.append(hit / len(case.gold_ids) if case.gold_ids else 1.0)
        precisions.append(hit / k)
        total_chars = sum(len(item.entry.content) for item in top)
        noise_chars = sum(len(item.entry.content) for item in top if item.entry.entry_id not in case.gold_ids)
        noises.append(noise_chars / total_chars if total_chars else 0.0)
        forbidden.append(len(set(ids) & case.must_not_ids) / len(case.must_not_ids) if case.must_not_ids else 0.0)
    return RecallMetrics(
        sum(recalls) / len(recalls),
        sum(precisions) / len(precisions),
        sum(noises) / len(noises),
        sum(forbidden) / len(forbidden),
    )


def memory_token_ratio(memory_text: str, total_prompt_text: str) -> float:
    """使用字符近似 token，避免评测依赖具体 provider tokenizer。"""
    if not total_prompt_text:
        return 0.0
    return len(memory_text) / max(1, len(total_prompt_text))
