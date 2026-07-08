"""Query engine tests against real tempfile storage (no service mocks)."""

from unittest.mock import MagicMock

import pytest

from clawdiney.query_engine import BrainQueryEngine
from clawdiney.storage import BrainStorage

DIM = 4


class FakeProvider:
    def embed(self, text):
        seed = float(len(text) % 97)
        return [seed, seed / 2, seed / 3, seed / 4]

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]


@pytest.fixture()
def vault_root(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    (root / "30_Resources" / "SOPs").mkdir(parents=True)
    (root / "SOP_Auth.md").write_text("# Auth SOP\n\nUse JWT.", encoding="utf-8")
    (root / "30_Resources" / "SOPs" / "SOP_Auth.md").write_text(
        "# Nested Auth SOP\n\n## Details\n\nnested version", encoding="utf-8"
    )
    (root / "Unique.md").write_text("# Unique\n\nonly one", encoding="utf-8")

    monkeypatch.delenv("VAULTS_DIR", raising=False)
    monkeypatch.delenv("VAULTS", raising=False)
    monkeypatch.setattr("clawdiney.config.Config.VAULT_PATH", str(root))
    monkeypatch.setattr("clawdiney.config.Config.ENABLE_RERANK", False)
    return root


@pytest.fixture()
def engine(vault_root, tmp_path):
    storage = BrainStorage(db_path=tmp_path / "brain.db", dimension=DIM)
    eng = BrainQueryEngine(vault="default", storage=storage, provider=FakeProvider())
    yield eng
    storage.close()


class TestInit:
    def test_no_vault_uses_default(self, engine):
        assert engine.current_vault == "default"

    def test_context_manager(self, vault_root, tmp_path):
        storage = BrainStorage(db_path=tmp_path / "cm.db", dimension=DIM)
        with BrainQueryEngine(
            vault="default", storage=storage, provider=FakeProvider()
        ) as eng:
            assert eng.current_vault == "default"


class TestFallbackChain:
    def test_basic_chain_appends_general(self, engine):
        engine.vault_config = None
        assert engine._get_fallback_chain() == ["default", "general"]

    def test_with_linked_vaults(self, engine):
        engine.current_vault = "design"
        engine.vault_config = MagicMock()
        engine.vault_config.linked_vaults = ["backend", "frontend"]
        assert engine._get_fallback_chain() == [
            "design",
            "backend",
            "frontend",
            "general",
        ]

    def test_general_not_duplicated(self, engine):
        engine.current_vault = "general"
        engine.vault_config = MagicMock()
        engine.vault_config.linked_vaults = []
        assert engine._get_fallback_chain() == ["general"]


class TestResolveNote:
    def test_exact_filename_ranks_first(self, engine):
        result = engine.resolve_note("SOP_Auth.md")
        assert len(result) == 2
        assert result[0]["score"] == 0

    def test_partial_match(self, engine):
        result = engine.resolve_note("unique")
        assert len(result) == 1
        assert result[0]["path"] == "Unique.md"

    def test_empty_query(self, engine):
        assert engine.resolve_note("  ") == []


class TestGetNoteByPath:
    def test_reads_canonical_path(self, engine):
        note = engine.get_note_by_path("Unique.md")
        assert note["filename"] == "Unique.md"
        assert "only one" in note["content"]

    def test_rejects_outside_vault(self, engine):
        with pytest.raises(ValueError, match="outside the vault"):
            engine.get_note_by_path("../../etc/passwd")

    def test_missing_note_raises(self, engine):
        with pytest.raises(FileNotFoundError):
            engine.get_note_by_path("nope.md")


class TestGetNoteChunks:
    def test_ambiguous_requires_disambiguation(self, engine):
        with pytest.raises(ValueError, match="Multiple notes match"):
            engine.get_note_chunks("SOP_Auth.md")

    def test_canonical_path_returns_chunks(self, engine):
        chunks = engine.get_note_chunks("30_Resources/SOPs/SOP_Auth.md")
        assert chunks
        assert all("header" in c and "chunk_index" in c for c in chunks)

    def test_unknown_raises(self, engine):
        with pytest.raises(FileNotFoundError):
            engine.get_note_chunks("does_not_exist.md")


class TestGetRelatedNotes:
    def test_uses_storage_scoped_by_current_vault(self, engine):
        engine.storage.upsert_note(
            vault="default",
            path="A.md",
            content_hash="h",
            updated_at="now",
            chunks=[{"header": "", "content": "a"}],
            embeddings=[[1.0, 2.0, 3.0, 4.0]],
            wikilinks=["Unique.md"],
            tags=[],
        )
        assert engine.get_related_notes("A.md") == ["Unique.md"]

    def test_vault_param_overrides(self, engine):
        assert engine.get_related_notes("A.md", vault="empty_vault") == []


class TestQueryMultiVault:
    def test_vault_override_prepends_chain(self, engine):
        engine.storage.upsert_note(
            vault="frontend",
            path="fe.md",
            content_hash="h",
            updated_at="now",
            chunks=[{"header": "", "content": "frontend widget catalog"}],
            embeddings=[[5.0, 2.5, 1.6, 1.25]],
            wikilinks=[],
            tags=[],
        )
        result = engine.query("widget", vault_override="frontend", expand_graph=False)
        assert "fe.md" in result
        assert "Source [frontend]" in result

    def test_results_tagged_with_vault_source(self, engine):
        engine.storage.upsert_note(
            vault="general",
            path="g.md",
            content_hash="h",
            updated_at="now",
            chunks=[{"header": "", "content": "general fallback zephyr"}],
            embeddings=[[9.0, 4.5, 3.0, 2.25]],
            wikilinks=[],
            tags=[],
        )
        result = engine.query("zephyr", expand_graph=False)
        assert "Source [general]: g.md" in result
