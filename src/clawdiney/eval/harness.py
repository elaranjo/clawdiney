"""Golden-query loading, fixture-vault indexing, and metric computation."""

import json
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..embedding_providers import EmbeddingProvider, default_provider
from ..indexer import _index_vault_inner
from ..query_engine import BrainQueryEngine
from ..storage import BrainStorage
from . import metrics as metrics_mod

logger = logging.getLogger(__name__)

EVAL_VAULT_NAME = "eval"


@dataclass
class GoldenQuery:
    query: str
    expected_paths: list[str]


@dataclass
class EvalResult:
    query: str
    expected_paths: list[str]
    retrieved_paths: list[str]
    recall_at_k: float
    reciprocal_rank: float
    hit: bool


@dataclass
class EvalRun:
    mode: str
    use_rerank: bool
    k: int
    results: list[EvalResult] = field(default_factory=list)

    @property
    def key(self) -> str:
        return f"{self.mode}+{'rerank' if self.use_rerank else 'norerank'}"

    def aggregate(self) -> dict[str, float]:
        return metrics_mod.aggregate(
            [
                {
                    "recall_at_k": r.recall_at_k,
                    "reciprocal_rank": r.reciprocal_rank,
                    "hit": r.hit,
                }
                for r in self.results
            ]
        )


def load_golden_queries(path: Path | str) -> list[GoldenQuery]:
    """Load newline-delimited JSON golden query records."""
    records = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            records.append(
                GoldenQuery(
                    query=data["query"], expected_paths=list(data["expected_paths"])
                )
            )
    return records


@contextmanager
def isolated_single_vault_config(vault_root: Path | str) -> Iterator[None]:
    """Force single-vault mode with VAULT_PATH=vault_root for the duration of the block.

    The eval harness indexes a fixture vault under an `eval` vault name that
    generally isn't a configured vault in the user's real (possibly
    multi-vault) setup; this makes `Config.get_vault_path` resolve any vault
    id to the fixture root instead of raising, without touching the user's
    real vault configuration.
    """
    from ..config import Config

    saved_vaults_dir = os.environ.pop("VAULTS_DIR", None)
    saved_vaults = os.environ.pop("VAULTS", None)
    saved_vault_path = Config.VAULT_PATH
    Config.VAULT_PATH = str(vault_root)
    try:
        yield
    finally:
        Config.VAULT_PATH = saved_vault_path
        if saved_vaults_dir is not None:
            os.environ["VAULTS_DIR"] = saved_vaults_dir
        if saved_vaults is not None:
            os.environ["VAULTS"] = saved_vaults


def build_fixture_index(
    fixture_vault_root: Path | str,
    db_path: Path | str,
    provider: EmbeddingProvider | None = None,
    dimension: int | None = None,
) -> BrainStorage:
    """Index the eval fixture vault into a fresh brain.db under EVAL_VAULT_NAME."""
    from ..config import Config

    provider = provider or default_provider()
    storage = BrainStorage(
        db_path=Path(db_path), dimension=dimension or Config.EMBEDDING_DIMENSION
    )
    summary = _index_vault_inner(
        vault_root=fixture_vault_root,
        storage=storage,
        vault_name=EVAL_VAULT_NAME,
        provider=provider,
    )
    logger.info(
        "Fixture vault indexed: %s/%s files, %s chunks",
        summary["processed_files"],
        summary["total_files"],
        summary["indexed_chunks"],
    )
    return storage


def run_eval(
    engine: BrainQueryEngine,
    golden_queries: list[GoldenQuery],
    mode: str = "hybrid",
    use_rerank: bool = True,
    k: int = 5,
    vault_override: str = EVAL_VAULT_NAME,
) -> EvalRun:
    """Run every golden query through engine.retrieve() and score it."""
    run = EvalRun(mode=mode, use_rerank=use_rerank, k=k)
    for gq in golden_queries:
        rows = engine.retrieve(
            gq.query,
            n_results=k,
            use_rerank=use_rerank,
            mode=mode,
            vault_override=vault_override,
        )
        retrieved_paths = [row["path"] for row in rows]
        run.results.append(
            EvalResult(
                query=gq.query,
                expected_paths=gq.expected_paths,
                retrieved_paths=retrieved_paths,
                recall_at_k=metrics_mod.recall_at_k(retrieved_paths, gq.expected_paths),
                reciprocal_rank=metrics_mod.reciprocal_rank(
                    retrieved_paths, gq.expected_paths
                ),
                hit=metrics_mod.hit(retrieved_paths, gq.expected_paths),
            )
        )
    return run


def load_baseline(path: Path | str) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        return {"k": None, "runs": {}}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_baseline(path: Path | str, baseline: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(baseline, fh, indent=2, sort_keys=True)
        fh.write("\n")


def check_regression(
    run: EvalRun, baseline: dict[str, Any], tolerance: float = 0.05
) -> list[str]:
    """Return a list of human-readable regression messages (empty = no regression)."""
    baseline_run = baseline.get("runs", {}).get(run.key)
    if baseline_run is None:
        return []
    current = run.aggregate()
    problems = []
    for metric_name, current_value in current.items():
        baseline_value = baseline_run.get(metric_name)
        if baseline_value is None:
            continue
        if current_value < baseline_value - tolerance:
            problems.append(
                f"{run.key}: {metric_name} dropped {baseline_value:.3f} -> "
                f"{current_value:.3f} (tolerance {tolerance:.3f})"
            )
    return problems
