"""Hybrid search tests: RRF fusion, fail-soft, dedup, engine query pipeline."""

from unittest.mock import patch

import pytest

from clawdiney.query_engine import BrainQueryEngine, rrf_fuse
from clawdiney.storage import BrainStorage

DIM = 4


class FakeProvider:
    def embed(self, text: str) -> list[float]:
        seed = float(len(text) % 97)
        return [seed, seed / 2, seed / 3, seed / 4]

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]


def _row(chunk_id, path="n.md", vault="default", content="c"):
    return {
        "chunk_id": chunk_id,
        "path": path,
        "vault": vault,
        "content": content,
        "header": "",
        "chunk_index": 0,
    }


class TestRrfFuse:
    def test_item_in_both_lists_wins(self):
        bm25 = [_row(1), _row(2)]
        vec = [_row(3), _row(1)]
        fused = rrf_fuse([bm25, vec])
        assert fused[0]["chunk_id"] == 1  # appears in both

    def test_single_list_preserves_order(self):
        fused = rrf_fuse([[_row(1), _row(2), _row(3)], []])
        assert [r["chunk_id"] for r in fused] == [1, 2, 3]

    def test_empty_lists(self):
        assert rrf_fuse([[], []]) == []


@pytest.fixture()
def engine(tmp_path, monkeypatch):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    monkeypatch.delenv("VAULTS_DIR", raising=False)
    monkeypatch.delenv("VAULTS", raising=False)
    monkeypatch.setenv("VAULT_PATH", str(vault_root))
    monkeypatch.setattr("clawdiney.config.Config.VAULT_PATH", str(vault_root))
    monkeypatch.setattr("clawdiney.config.Config.ENABLE_RERANK", False)

    storage = BrainStorage(db_path=tmp_path / "brain.db", dimension=DIM)
    provider = FakeProvider()

    def _index(path, content, seed):
        storage.upsert_note(
            vault="default",
            path=path,
            content_hash=f"h-{path}",
            updated_at="now",
            chunks=[{"header": "", "content": content}],
            embeddings=[[seed, seed / 2, seed / 3, seed / 4]],
            wikilinks=[],
            tags=[],
        )

    _index("exact.md", "the zorbulator protocol spec", seed=50.0)
    _index("semantic.md", "notes about authentication flows", seed=3.0)
    _index("other.md", "cooking recipes collection", seed=80.0)

    eng = BrainQueryEngine(vault="default", storage=storage, provider=provider)
    yield eng, storage
    storage.close()


class TestEngineQuery:
    def test_exact_term_found_via_bm25(self, engine):
        eng, _ = engine
        # embedding of query won't match seed 50, but BM25 will hit "zorbulator"
        result = eng.query("zorbulator", n_results=2, expand_graph=False)
        assert "exact.md" in result

    def test_vector_side_found_when_bm25_misses(self, engine):
        eng, _ = engine
        # query with no shared keywords; FakeProvider embeds by length —
        # craft query whose length matches semantic.md's seed neighborhood
        with patch.object(eng.storage, "search_bm25", return_value=[]):
            result = eng.query("abc", n_results=1, expand_graph=False)
        assert "--- Source" in result  # vector side alone still returns results

    def test_bm25_failure_fail_soft(self, engine):
        eng, _ = engine
        with patch.object(
            eng.storage, "search_bm25", side_effect=RuntimeError("fts broke")
        ):
            result = eng.query("anything", n_results=2, expand_graph=False)
        assert isinstance(result, str)  # no exception; vector results only

    def test_vector_failure_fail_soft(self, engine):
        eng, _ = engine
        with patch.object(eng, "get_embedding", side_effect=ConnectionError("down")):
            result = eng.query("zorbulator", n_results=2, expand_graph=False)
        assert "exact.md" in result  # BM25 alone survives

    def test_both_fail_returns_empty_briefing(self, engine):
        eng, _ = engine
        with (
            patch.object(eng.storage, "search_bm25", side_effect=RuntimeError("x")),
            patch.object(eng, "get_embedding", side_effect=ConnectionError("y")),
        ):
            assert eng.query("anything", expand_graph=False) == ""

    def test_dedup_by_note(self, engine):
        eng, storage = engine
        # add second chunk to exact.md
        storage.upsert_note(
            vault="default",
            path="exact.md",
            content_hash="h2",
            updated_at="now",
            chunks=[
                {"header": "a", "content": "zorbulator part one"},
                {"header": "b", "content": "zorbulator part two"},
            ],
            embeddings=[[50.0, 25.0, 16.6, 12.5], [50.0, 25.0, 16.7, 12.5]],
            wikilinks=[],
            tags=[],
        )
        result = eng.query("zorbulator", n_results=5, expand_graph=False)
        assert result.count("exact.md") == 1

    def test_hostile_fts_inputs(self, engine):
        eng, _ = engine
        for hostile in ('"unbalanced', "a NEAR/3 b", "wild*card", "((("):
            eng.query(hostile, n_results=2, expand_graph=False)  # must not raise


class TestAgentScopedQuery:
    def test_default_agent_matches_no_agent_param(self, engine):
        eng, _ = engine
        with_default = eng.query(
            "zorbulator", n_results=2, expand_graph=False, agent_id="default"
        )
        without_param = eng.query("zorbulator", n_results=2, expand_graph=False)
        assert with_default == without_param

    def test_cross_agent_isolation(self, engine):
        eng, storage = engine
        storage.upsert_note(
            vault="default",
            path="40_Memory/agent-a/secret.md",
            content_hash="h",
            updated_at="now",
            chunks=[{"header": "", "content": "zorbulator agent-a private note"}],
            embeddings=[[50.0, 25.0, 16.6, 12.5]],
            wikilinks=[],
            tags=[],
            agent_id="agent-a",
        )
        seen_by_b = eng.query(
            "zorbulator", n_results=5, expand_graph=False, agent_id="agent-b"
        )
        assert "40_Memory/agent-a/secret.md" not in seen_by_b

        seen_by_a = eng.query(
            "zorbulator", n_results=5, expand_graph=False, agent_id="agent-a"
        )
        assert "40_Memory/agent-a/secret.md" in seen_by_a
        # agent-a still sees shared/default content too
        assert "exact.md" in seen_by_a

    def test_explicit_agent_query_still_returns_shared_content(self, engine):
        eng, _ = engine
        result = eng.query(
            "zorbulator", n_results=5, expand_graph=False, agent_id="agent-b"
        )
        assert "exact.md" in result
