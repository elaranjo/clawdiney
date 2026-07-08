"""Tests for the embedded SQLite storage layer (real tempfile DB, no mocks)."""

import threading

import pytest

from clawdiney.storage import (
    BrainStorage,
    SchemaMismatchError,
    sanitize_fts_query,
)

DIM = 4


@pytest.fixture()
def storage(tmp_path):
    store = BrainStorage(db_path=tmp_path / "brain.db", dimension=DIM)
    yield store
    store.close()


def _vec(seed: float) -> list[float]:
    return [seed, seed / 2, seed / 3, seed / 4]


def _index_note(
    store, path, content, vault="default", wikilinks=None, tags=None, seed=1.0
):
    return store.upsert_note(
        vault=vault,
        path=path,
        content_hash=f"hash-{path}-{content[:8]}",
        updated_at="2026-07-08T00:00:00",
        chunks=[{"header": "H1", "content": content}],
        embeddings=[_vec(seed)],
        wikilinks=wikilinks or [],
        tags=tags or [],
    )


class TestSchema:
    def test_creates_all_tables(self, storage):
        tables = {
            row["name"]
            for row in storage.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        for expected in ("documents", "chunks", "entities", "relations", "meta"):
            assert expected in tables
        assert "chunk_vectors" in tables  # vec0 virtual table
        assert "chunk_fts" in tables

    def test_meta_records_model_and_dimension(self, storage):
        stats = storage.stats()
        assert stats["meta"]["embedding_dimension"] == str(DIM)
        assert stats["meta"]["embedding_model"]

    def test_dimension_mismatch_raises(self, tmp_path):
        db = tmp_path / "brain.db"
        BrainStorage(db_path=db, dimension=DIM).close()
        with pytest.raises(SchemaMismatchError, match="Re-index required"):
            BrainStorage(db_path=db, dimension=DIM + 1)

    def test_per_thread_connections(self, storage):
        conns = {}

        def grab(key):
            conns[key] = id(storage.conn)
            storage.close()

        t = threading.Thread(target=grab, args=("other",))
        t.start()
        t.join()
        conns["main"] = id(storage.conn)
        assert conns["main"] != conns["other"]


class TestFtsTriggerSync:
    def test_insert_indexed(self, storage):
        _index_note(storage, "a.md", "unique alpha content")
        rows = storage.conn.execute(
            "SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH '\"alpha\"'"
        ).fetchall()
        assert len(rows) == 1

    def test_reindex_replaces_fts(self, storage):
        _index_note(storage, "a.md", "old body text")
        _index_note(storage, "a.md", "new body text")
        assert not storage.conn.execute(
            "SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH '\"old\"'"
        ).fetchall()
        assert storage.conn.execute(
            "SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH '\"new\"'"
        ).fetchall()

    def test_delete_removes_fts_vectors_and_chunks(self, storage):
        _index_note(storage, "a.md", "doomed content")
        removed = storage.delete_note("default", "a.md")
        assert removed == 1
        assert not storage.conn.execute(
            "SELECT rowid FROM chunk_fts WHERE chunk_fts MATCH '\"doomed\"'"
        ).fetchall()
        assert storage.conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0] == 0
        assert (
            storage.conn.execute("SELECT COUNT(*) FROM chunk_vectors").fetchone()[0]
            == 0
        )


class TestUpsertNote:
    def test_chunk_embedding_length_mismatch_raises(self, storage):
        with pytest.raises(ValueError, match="mismatch"):
            storage.upsert_note(
                vault="default",
                path="a.md",
                content_hash="h",
                updated_at="now",
                chunks=[{"header": "", "content": "x"}],
                embeddings=[],
                wikilinks=[],
                tags=[],
            )

    def test_reindex_idempotent_relations(self, storage):
        for _ in range(2):
            _index_note(storage, "a.md", "body", wikilinks=["B"], tags=["tag1"])
        assert storage.conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0] == 2

    def test_document_hashes(self, storage):
        _index_note(storage, "a.md", "body one")
        hashes = storage.get_document_hashes("default")
        assert list(hashes) == ["a.md"]


class TestSearch:
    def test_bm25_exact_term(self, storage):
        _index_note(storage, "a.md", "the flux capacitor design", seed=1.0)
        _index_note(storage, "b.md", "general note about cooking", seed=2.0)
        results = storage.search_bm25("flux capacitor", ["default"], k=5)
        assert results and results[0]["path"] == "a.md"

    def test_bm25_hostile_inputs(self, storage):
        _index_note(storage, "a.md", "safe content here")
        for hostile in ('"unbalanced', "a NEAR/3 b", "wild*card", "(((", 'x OR "'):
            storage.search_bm25(hostile, ["default"], k=5)  # must not raise

    def test_sanitize_fts_query(self):
        assert sanitize_fts_query('"quoted" AND (x)') == '"quoted" OR "AND" OR "x"'
        assert sanitize_fts_query("!!!") == ""

    def test_vector_knn_orders_by_distance(self, storage):
        _index_note(storage, "near.md", "content near", seed=1.0)
        _index_note(storage, "far.md", "content far", seed=10.0)
        results = storage.search_vectors(_vec(1.1), ["default"], k=2)
        assert [r["path"] for r in results] == ["near.md", "far.md"]

    def test_vault_isolation_in_search(self, storage):
        _index_note(storage, "a.md", "isolation test body", vault="v1", seed=1.0)
        _index_note(storage, "b.md", "isolation test body", vault="v2", seed=1.0)
        bm25 = storage.search_bm25("isolation", ["v1"], k=10)
        assert {r["vault"] for r in bm25} == {"v1"}
        knn = storage.search_vectors(_vec(1.0), ["v1"], k=10)
        assert {r["vault"] for r in knn} == {"v1"}

    def test_empty_vaults_returns_empty(self, storage):
        assert storage.search_bm25("x", [], 5) == []
        assert storage.search_vectors(_vec(1.0), [], 5) == []


class TestGraph:
    def test_wikilink_neighbors_bidirectional(self, storage):
        _index_note(storage, "B.md", "b body")
        _index_note(storage, "A.md", "a body", wikilinks=["B.md"])
        _index_note(storage, "C.md", "c body", wikilinks=["A.md"])
        related = storage.get_related_notes("A.md", "default")
        assert set(related) == {"B.md", "C.md"}

    def test_wikilink_by_name_dangling_target(self, storage):
        _index_note(storage, "A.md", "a body", wikilinks=["Missing Note"])
        related = storage.get_related_notes("A.md", "default")
        assert related == ["Missing Note"]  # path is NULL, falls back to name

    def test_tag_neighbors(self, storage):
        _index_note(storage, "A.md", "a", tags=["auth"])
        _index_note(storage, "B.md", "b", tags=["auth"])
        assert storage.get_related_notes("A.md", "default") == ["B.md"]

    def test_unknown_note_returns_empty(self, storage):
        assert storage.get_related_notes("nope.md", "default") == []

    def test_cross_vault_isolation(self, storage):
        _index_note(storage, "A.md", "a", vault="v1", tags=["shared"])
        _index_note(storage, "B.md", "b", vault="v2", tags=["shared"])
        assert storage.get_related_notes("A.md", "v1") == []

    def test_two_hop_expansion(self, storage):
        _index_note(storage, "C.md", "c")
        _index_note(storage, "B.md", "b", wikilinks=["C.md"])
        _index_note(storage, "A.md", "a", wikilinks=["B.md"])
        result = storage.expand_neighborhood("A.md", "default", depth=2)
        by_name = {r["name"]: r["distance"] for r in result}
        assert by_name["B.md"] == 1
        assert by_name["C.md"] == 2

    def test_cycle_terminates_min_distance(self, storage):
        _index_note(storage, "B.md", "b", wikilinks=["A.md"])
        _index_note(storage, "A.md", "a", wikilinks=["B.md"])
        result = storage.expand_neighborhood("A.md", "default", depth=3)
        names = [r["name"] for r in result]
        assert names.count("B.md") == 1
        assert {r["distance"] for r in result if r["name"] == "B.md"} == {1}

    def test_deleted_note_relations_removed(self, storage):
        _index_note(storage, "B.md", "b")
        _index_note(storage, "A.md", "a", wikilinks=["B.md"], tags=["t"])
        storage.delete_note("default", "A.md")
        assert storage.conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0] == 0
        # orphan tag pruned
        assert (
            storage.conn.execute(
                "SELECT COUNT(*) FROM entities WHERE kind='tag'"
            ).fetchone()[0]
            == 0
        )


class TestDanglingLinkResolution:
    def test_link_without_extension_resolves_to_note(self, storage):
        _index_note(storage, "Backend.md", "b body")
        _index_note(storage, "A.md", "a body", wikilinks=["Backend"])
        assert storage.get_related_notes("A.md", "default") == ["Backend.md"]
        # no dangling duplicate entity
        n = storage.conn.execute(
            "SELECT COUNT(*) FROM entities WHERE kind='note' AND path IS NULL"
        ).fetchone()[0]
        assert n == 0

    def test_dangling_adopted_when_note_appears_later(self, storage):
        _index_note(storage, "A.md", "a body", wikilinks=["Later"])
        _index_note(storage, "Later.md", "arrives later")
        related = storage.get_related_notes("A.md", "default")
        assert related == ["Later.md"]
