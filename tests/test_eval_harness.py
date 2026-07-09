"""Eval harness unit tests: metrics correctness and harness wiring (no live Ollama)."""

from clawdiney.eval import metrics
from clawdiney.eval.harness import (
    GoldenQuery,
    build_fixture_index,
    isolated_single_vault_config,
    load_golden_queries,
    run_eval,
)
from clawdiney.query_engine import BrainQueryEngine

DIM = 4


class FakeProvider:
    def embed(self, text: str) -> list[float]:
        seed = float(len(text) % 97)
        return [seed, seed / 2, seed / 3, seed / 4]

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]


class TestRecallAtK:
    def test_all_expected_found(self):
        assert metrics.recall_at_k(["a.md", "b.md"], ["a.md", "b.md"]) == 1.0

    def test_partial_found(self):
        assert metrics.recall_at_k(["a.md", "c.md"], ["a.md", "b.md"]) == 0.5

    def test_none_found(self):
        assert metrics.recall_at_k(["c.md"], ["a.md", "b.md"]) == 0.0

    def test_no_expected_paths(self):
        assert metrics.recall_at_k(["a.md"], []) == 0.0


class TestReciprocalRank:
    def test_first_rank_hit(self):
        assert metrics.reciprocal_rank(["a.md", "b.md"], ["a.md"]) == 1.0

    def test_third_rank_hit(self):
        assert metrics.reciprocal_rank(["x.md", "y.md", "a.md"], ["a.md"]) == 1 / 3

    def test_no_hit(self):
        assert metrics.reciprocal_rank(["x.md"], ["a.md"]) == 0.0


class TestHit:
    def test_hit_true(self):
        assert metrics.hit(["a.md", "x.md"], ["a.md"]) is True

    def test_hit_false(self):
        assert metrics.hit(["x.md"], ["a.md"]) is False


class TestAggregate:
    def test_empty(self):
        assert metrics.aggregate([]) == {
            "recall_at_k": 0.0,
            "mrr": 0.0,
            "hit_rate": 0.0,
        }

    def test_mean_across_queries(self):
        per_query = [
            {"recall_at_k": 1.0, "reciprocal_rank": 1.0, "hit": True},
            {"recall_at_k": 0.0, "reciprocal_rank": 0.0, "hit": False},
        ]
        agg = metrics.aggregate(per_query)
        assert agg["recall_at_k"] == 0.5
        assert agg["mrr"] == 0.5
        assert agg["hit_rate"] == 0.5


class TestLoadGoldenQueries:
    def test_loads_jsonl(self, tmp_path):
        path = tmp_path / "golden.jsonl"
        path.write_text(
            '{"query": "q1", "expected_paths": ["a.md"]}\n'
            "\n"
            '{"query": "q2", "expected_paths": ["b.md", "c.md"]}\n',
            encoding="utf-8",
        )
        queries = load_golden_queries(path)
        assert len(queries) == 2
        assert queries[0] == GoldenQuery(query="q1", expected_paths=["a.md"])
        assert queries[1].expected_paths == ["b.md", "c.md"]


class TestRunEvalAgainstFixtureIndex:
    def test_exact_term_query_hits_via_bm25(self, tmp_path, monkeypatch):
        monkeypatch.setattr("clawdiney.config.Config.ENABLE_RERANK", False)

        vault_root = tmp_path / "fixture_vault"
        vault_root.mkdir()
        (vault_root / "zorbulator.md").write_text(
            "# Zorbulator\n\nthe zorbulator protocol spec", encoding="utf-8"
        )
        (vault_root / "other.md").write_text(
            "# Other\n\ncooking recipes collection", encoding="utf-8"
        )

        db_path = tmp_path / "eval.db"
        storage = build_fixture_index(vault_root, db_path, provider=FakeProvider(), dimension=DIM)

        with isolated_single_vault_config(vault_root):
            engine = BrainQueryEngine(vault="eval", storage=storage, provider=FakeProvider())

        golden = [GoldenQuery(query="zorbulator", expected_paths=["zorbulator.md"])]
        run = run_eval(engine, golden, mode="bm25", use_rerank=False, k=2)
        engine.close()

        assert run.results[0].hit is True
        assert run.results[0].recall_at_k == 1.0
        agg = run.aggregate()
        assert agg["hit_rate"] == 1.0

    def test_no_hit_when_query_matches_nothing(self, tmp_path, monkeypatch):
        monkeypatch.setattr("clawdiney.config.Config.ENABLE_RERANK", False)

        vault_root = tmp_path / "fixture_vault"
        vault_root.mkdir()
        (vault_root / "note.md").write_text("# Note\n\nunrelated content", encoding="utf-8")

        db_path = tmp_path / "eval.db"
        storage = build_fixture_index(vault_root, db_path, provider=FakeProvider(), dimension=DIM)

        with isolated_single_vault_config(vault_root):
            engine = BrainQueryEngine(vault="eval", storage=storage, provider=FakeProvider())

        golden = [GoldenQuery(query="note", expected_paths=["does_not_exist.md"])]
        run = run_eval(engine, golden, mode="hybrid", use_rerank=False, k=2)
        engine.close()

        assert run.results[0].hit is False
        assert run.aggregate()["hit_rate"] == 0.0


class TestIsolatedSingleVaultConfig:
    def test_restores_env_after_block(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VAULTS_DIR", "/some/dir")
        from clawdiney.config import Config

        original_vault_path = Config.VAULT_PATH
        with isolated_single_vault_config(tmp_path):
            import os

            assert "VAULTS_DIR" not in os.environ
            assert Config.VAULT_PATH == str(tmp_path)

        import os

        assert os.environ["VAULTS_DIR"] == "/some/dir"
        assert Config.VAULT_PATH == original_vault_path
