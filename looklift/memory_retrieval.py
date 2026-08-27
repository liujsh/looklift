"""Context Memory 的本地混合召回器：BM25 + 可选向量 + RRF。"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Iterable, Mapping, Sequence

from .context_memory import ContextEntry

_TOKEN_RE = re.compile(r"[\u4e00-\u9fff]|[a-z0-9_./-]+", re.I)


@dataclass(frozen=True)
class RecallQuery:
    text: str
    project_id: str | None = None
    run_id: str | None = None
    artifact_type: str | None = None
    token_budget: int = 6000


@dataclass(frozen=True)
class RetrievedMemory:
    entry: ContextEntry
    rank: int
    sources: tuple[str, ...]
    score: float
    reason: str


def _tokens(value: str) -> list[str]:
    result: list[str] = []
    for token in _TOKEN_RE.findall(value.casefold()):
        result.append(token)
        if len(token) > 1 and not token.isascii():
            result.extend(token[i : i + 2] for i in range(len(token) - 1))
    return result


def _searchable(entry: ContextEntry) -> str:
    return " ".join((entry.name, entry.description, entry.content, entry.evidence))


class HybridMemoryRetriever:
    def __init__(self, *, rrf_k: int = 60) -> None:
        if rrf_k <= 0:
            raise ValueError("rrf_k 必须为正数")
        self.rrf_k = rrf_k

    def retrieve(
        self,
        entries: Iterable[ContextEntry],
        query: RecallQuery,
        *,
        embed_query: Callable[[str], Sequence[float]] | None = None,
        embeddings: Mapping[str, Sequence[float]] | None = None,
    ) -> tuple[RetrievedMemory, ...]:
        candidates = [item for item in entries if self._eligible(item, query)]
        if not candidates or query.token_budget <= 0:
            return ()
        lexical = self._bm25(candidates, query.text)
        dense: dict[str, float] = {}
        if embed_query is not None and embeddings:
            vector = list(embed_query(query.text))
            if vector:
                dense = {
                    item.entry_id: self._cosine(vector, embeddings[item.entry_id])
                    for item in candidates
                    if item.entry_id in embeddings
                }
        lexical_order = [item.entry_id for item, score in sorted(lexical.items(), key=lambda pair: (-pair[1], pair[0].entry_id)) if score > 0]
        dense_order = [entry_id for entry_id, _ in sorted(dense.items(), key=lambda pair: (-pair[1], pair[0]))]
        ranks: dict[str, float] = {}
        sources: dict[str, set[str]] = {}
        for rank, entry_id in enumerate(lexical_order, 1):
            ranks[entry_id] = ranks.get(entry_id, 0) + 1 / (self.rrf_k + rank)
            sources.setdefault(entry_id, set()).add("bm25")
        for rank, entry_id in enumerate(dense_order, 1):
            ranks[entry_id] = ranks.get(entry_id, 0) + 1 / (self.rrf_k + rank)
            sources.setdefault(entry_id, set()).add("vector")
        by_id = {item.entry_id: item for item in candidates}
        ordered = sorted(ranks, key=lambda entry_id: (-ranks[entry_id], self._tie_key(by_id[entry_id])))
        result: list[RetrievedMemory] = []
        used_groups: set[str] = set()
        used_tokens = 0
        for entry_id in ordered:
            item = by_id[entry_id]
            group = item.description.split("#group:", 1)[1].split()[0] if "#group:" in item.description else ""
            if group and group in used_groups:
                continue
            cost = max(1, len(item.content) // 4)
            if used_tokens + cost > query.token_budget:
                continue
            used_tokens += cost
            if group:
                used_groups.add(group)
            result.append(RetrievedMemory(item, len(result) + 1, tuple(sorted(sources[entry_id])), ranks[entry_id], "hybrid" if len(sources[entry_id]) > 1 else next(iter(sources[entry_id]))))
        return tuple(result)

    @staticmethod
    def _eligible(item: ContextEntry, query: RecallQuery) -> bool:
        if not item.enabled or item.state != "active" or HybridMemoryRetriever._expired(item):
            return False
        if item.scope == "project" and item.project_id != query.project_id:
            return False
        if item.scope == "run" and item.run_id != query.run_id:
            return False
        if item.entry_type == "rule" and item.description and "#artifact:" in item.description:
            allowed = item.description.split("#artifact:", 1)[1].split()[0].split(",")
            if query.artifact_type not in allowed:
                return False
        return True

    @staticmethod
    def _expired(item: ContextEntry) -> bool:
        if not item.expires_at:
            return False
        try:
            return datetime.fromisoformat(item.expires_at) <= datetime.now(timezone.utc)
        except ValueError:
            return True

    @staticmethod
    def _bm25(entries: list[ContextEntry], text: str) -> dict[ContextEntry, float]:
        query_terms = _tokens(text)
        if not query_terms:
            return {item: 0.0 for item in entries}
        docs = [_tokens(_searchable(item)) for item in entries]
        avgdl = sum(len(doc) for doc in docs) / max(1, len(docs))
        document_frequency: dict[str, int] = {}
        for doc in docs:
            for term in set(doc):
                document_frequency[term] = document_frequency.get(term, 0) + 1
        scores: dict[ContextEntry, float] = {}
        for item, doc in zip(entries, docs):
            frequencies = {term: doc.count(term) for term in set(doc)}
            score = 0.0
            for term in query_terms:
                if term not in frequencies:
                    continue
                df = document_frequency[term]
                idf = math.log(1 + (len(entries) - df + 0.5) / (df + 0.5))
                tf = frequencies[term]
                score += idf * (tf * 2.2) / (tf + 1.2 * (0.25 + 0.75 * len(doc) / max(1, avgdl)))
            scores[item] = score
        return scores

    @staticmethod
    def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
        if len(left) != len(right):
            return 0.0
        dot = sum(a * b for a, b in zip(left, right))
        left_norm = math.sqrt(sum(a * a for a in left))
        right_norm = math.sqrt(sum(b * b for b in right))
        return dot / (left_norm * right_norm) if left_norm and right_norm else 0.0

    @staticmethod
    def _tie_key(item: ContextEntry) -> tuple[int, str, str]:
        scope_rank = {"run": 0, "project": 1, "global": 2}.get(item.scope, 3)
        return scope_rank, item.updated_at, item.entry_id
