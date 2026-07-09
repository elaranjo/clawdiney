"""`clawdiney-eval` CLI: run the retrieval eval harness against the fixture vault."""

import argparse
import logging
import sys
import tempfile
from pathlib import Path

from ..logging_config import setup_logging
from ..query_engine import BrainQueryEngine
from . import harness

logger = logging.getLogger(__name__)

DEFAULT_FIXTURE_VAULT = (
    Path(__file__).resolve().parents[3] / "tests" / "eval" / "fixture_vault"
)
DEFAULT_GOLDEN_QUERIES = (
    Path(__file__).resolve().parents[3] / "tests" / "eval" / "golden_queries.jsonl"
)
DEFAULT_BASELINE = (
    Path(__file__).resolve().parents[3] / "tests" / "eval" / "baseline.json"
)

ALL_RUN_CONFIGS: list[tuple[str, bool]] = [
    ("hybrid", True),
    ("hybrid", False),
    ("bm25", False),
    ("vector", False),
]


def _print_run(run: harness.EvalRun) -> None:
    agg = run.aggregate()
    print(
        f"{run.key:<20} recall@{run.k}={agg['recall_at_k']:.3f}  "
        f"mrr={agg['mrr']:.3f}  hit_rate={agg['hit_rate']:.3f}"
    )


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(
        description="Run the Clawdiney retrieval evaluation harness against the fixture vault."
    )
    parser.add_argument("--fixture-vault", type=Path, default=DEFAULT_FIXTURE_VAULT)
    parser.add_argument("--golden", type=Path, default=DEFAULT_GOLDEN_QUERIES)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument(
        "--db",
        type=Path,
        default=None,
        help="Reuse an already-indexed brain.db instead of re-indexing",
    )
    parser.add_argument("--k", type=int, default=5)
    parser.add_argument(
        "--mode", choices=["hybrid", "bm25", "vector"], default="hybrid"
    )
    rerank_group = parser.add_mutually_exclusive_group()
    rerank_group.add_argument(
        "--rerank", dest="rerank", action="store_true", default=None
    )
    rerank_group.add_argument("--no-rerank", dest="rerank", action="store_false")
    parser.add_argument(
        "--all-modes",
        action="store_true",
        help="Run hybrid+rerank, hybrid, bm25, and vector-only and print all four",
    )
    parser.add_argument(
        "--update-baseline",
        action="store_true",
        help="Write current results into the baseline file instead of checking regression",
    )
    parser.add_argument("--tolerance", type=float, default=0.05)
    args = parser.parse_args()

    golden_queries = harness.load_golden_queries(args.golden)
    if not golden_queries:
        logger.error("No golden queries loaded from %s", args.golden)
        sys.exit(2)

    use_temp_db = args.db is None
    db_path = args.db or Path(tempfile.mkstemp(suffix=".db")[1])

    try:
        storage = harness.build_fixture_index(args.fixture_vault, db_path)
        with harness.isolated_single_vault_config(args.fixture_vault):
            engine = BrainQueryEngine(vault=harness.EVAL_VAULT_NAME, storage=storage)

        run_configs = (
            ALL_RUN_CONFIGS
            if args.all_modes
            else [(args.mode, args.rerank if args.rerank is not None else True)]
        )

        runs = []
        for mode, use_rerank in run_configs:
            run = harness.run_eval(
                engine, golden_queries, mode=mode, use_rerank=use_rerank, k=args.k
            )
            runs.append(run)
            _print_run(run)

        engine.close()

        if args.update_baseline:
            baseline = harness.load_baseline(args.baseline)
            baseline["k"] = args.k
            baseline.setdefault("runs", {})
            for run in runs:
                baseline["runs"][run.key] = run.aggregate()
            harness.save_baseline(args.baseline, baseline)
            print(f"Baseline updated: {args.baseline}")
            sys.exit(0)

        baseline = harness.load_baseline(args.baseline)
        all_problems: list[str] = []
        for run in runs:
            all_problems.extend(
                harness.check_regression(run, baseline, tolerance=args.tolerance)
            )

        if all_problems:
            print("\nREGRESSION DETECTED:")
            for problem in all_problems:
                print(f"  - {problem}")
            sys.exit(1)

        print("\nNo regression vs baseline.")
        sys.exit(0)
    finally:
        if use_temp_db and db_path.exists():
            db_path.unlink()


if __name__ == "__main__":
    main()
