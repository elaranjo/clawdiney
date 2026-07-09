"""Retrieval quality metrics: recall@k, reciprocal rank, hit rate."""

from collections.abc import Iterable


def recall_at_k(retrieved_paths: Iterable[str], expected_paths: Iterable[str]) -> float:
    """Fraction of expected paths present anywhere in retrieved_paths (already top-k)."""
    expected = set(expected_paths)
    if not expected:
        return 0.0
    hits = len(set(retrieved_paths) & expected)
    return hits / len(expected)


def reciprocal_rank(retrieved_paths: Iterable[str], expected_paths: Iterable[str]) -> float:
    """1/rank of the first retrieved path that is in expected_paths, else 0.0."""
    expected = set(expected_paths)
    for rank, path in enumerate(retrieved_paths, start=1):
        if path in expected:
            return 1.0 / rank
    return 0.0


def hit(retrieved_paths: Iterable[str], expected_paths: Iterable[str]) -> bool:
    """Whether any expected path appears in retrieved_paths."""
    return bool(set(retrieved_paths) & set(expected_paths))


def aggregate(per_query_metrics: list[dict[str, float]]) -> dict[str, float]:
    """Mean recall_at_k / reciprocal_rank / hit_rate across queries."""
    if not per_query_metrics:
        return {"recall_at_k": 0.0, "mrr": 0.0, "hit_rate": 0.0}
    n = len(per_query_metrics)
    return {
        "recall_at_k": sum(m["recall_at_k"] for m in per_query_metrics) / n,
        "mrr": sum(m["reciprocal_rank"] for m in per_query_metrics) / n,
        "hit_rate": sum(1.0 if m["hit"] else 0.0 for m in per_query_metrics) / n,
    }
