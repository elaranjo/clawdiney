"""End-to-end indexing pipeline tests: vault fixture -> brain.db (fake embedder)."""

import pytest

from clawdiney.incremental_indexer import IncrementalIndexer, incremental_sync
from clawdiney.indexer import extract_wikilinks, index_vault
from clawdiney.storage import BrainStorage

DIM = 4


class FakeProvider:
    """Deterministic embedder: vector derived from text length."""

    def embed(self, text: str) -> list[float]:
        seed = float(len(text) % 97)
        return [seed, seed / 2, seed / 3, seed / 4]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return [self.embed(t) for t in texts]


@pytest.fixture()
def vault(tmp_path):
    root = tmp_path / "vault"
    (root / "sub").mkdir(parents=True)
    (root / "A.md").write_text(
        "# Alpha\n\nLinks to [[B]] and tagged #auth\n\nflux capacitor design",
        encoding="utf-8",
    )
    (root / "B.md").write_text("# Beta\n\nAlso #auth related", encoding="utf-8")
    (root / "sub" / "C.md").write_text("# Gamma\n\nStandalone note", encoding="utf-8")
    (root / "empty.md").write_text("", encoding="utf-8")
    return root


@pytest.fixture()
def storage(tmp_path):
    store = BrainStorage(db_path=tmp_path / "brain.db", dimension=DIM)
    yield store
    store.close()


def test_extract_wikilinks_aliases_and_anchors():
    content = "[[Target|Alias]] [[Other#Section]] [[Plain]]"
    assert extract_wikilinks(content) == ["Target", "Other", "Plain"]


class TestFullIndex:
    def test_index_vault_populates_all_tables(self, vault, storage):
        summary = index_vault(vault, storage=storage, provider=FakeProvider())
        assert summary["processed_files"] == 3  # empty.md skipped
        assert summary["indexed_chunks"] >= 3

        stats = storage.stats()
        assert stats["counts"]["documents"] == 3
        assert stats["counts"]["chunks"] >= 3
        # A links to B (LINKS_TO) + A,B tagged auth (2x HAS_TAG)
        assert stats["counts"]["relations"] >= 3
        # vectors match chunks
        n_vec = storage.conn.execute("SELECT COUNT(*) FROM chunk_vectors").fetchone()[0]
        assert n_vec == stats["counts"]["chunks"]

    def test_graph_relations_from_vault(self, vault, storage):
        index_vault(vault, storage=storage, provider=FakeProvider())
        related = storage.get_related_notes("A.md", "default")
        # B reachable via wikilink AND shared tag; deduplicated
        assert "B" in related or "B.md" in related

    def test_fts_searchable_after_index(self, vault, storage):
        index_vault(vault, storage=storage, provider=FakeProvider())
        results = storage.search_bm25("flux capacitor", ["default"], k=5)
        assert results and results[0]["path"] == "A.md"

    def test_reindex_idempotent(self, vault, storage):
        index_vault(vault, storage=storage, provider=FakeProvider())
        first = storage.stats()["counts"]
        index_vault(vault, storage=storage, provider=FakeProvider())
        second = storage.stats()["counts"]
        assert first == second


class TestIncrementalSync:
    def test_initial_sync_indexes_everything(self, vault, storage):
        result = incremental_sync(
            vault_root=vault, storage=storage, provider=FakeProvider()
        )
        assert result["files_synced"] == 3
        assert result["sync_type"] == "incremental"

    def test_unchanged_files_skipped(self, vault, storage):
        incremental_sync(vault_root=vault, storage=storage, provider=FakeProvider())
        result = incremental_sync(
            vault_root=vault, storage=storage, provider=FakeProvider()
        )
        assert result["files_synced"] == 0

    def test_modified_file_resynced(self, vault, storage):
        incremental_sync(vault_root=vault, storage=storage, provider=FakeProvider())
        (vault / "B.md").write_text("# Beta v2\n\nchanged body", encoding="utf-8")
        result = incremental_sync(
            vault_root=vault, storage=storage, provider=FakeProvider()
        )
        assert result["files_synced"] == 1
        assert storage.search_bm25("changed", ["default"], k=5)

    def test_deleted_file_removed(self, vault, storage):
        incremental_sync(vault_root=vault, storage=storage, provider=FakeProvider())
        (vault / "sub" / "C.md").unlink()
        result = incremental_sync(
            vault_root=vault, storage=storage, provider=FakeProvider()
        )
        assert result["files_deleted"] == 1
        assert "sub/C.md" not in storage.get_document_hashes("default")

    def test_detect_changes(self, vault, storage):
        indexer = IncrementalIndexer(vault, storage=storage, provider=FakeProvider())
        changes, deleted = indexer.detect_changes()
        # 4 files on disk never indexed (incl. empty.md, skipped only at sync time)
        assert len(changes) == 4
        assert deleted == []
