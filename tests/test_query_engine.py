from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from clawdiney.query_engine import BrainQueryEngine


@pytest.fixture
def mock_deps():
    with (
        patch("clawdiney.query_engine.Config.get_chroma_client_config", return_value={"host": "localhost", "port": "8000"}),
        patch("clawdiney.query_engine.chromadb.HttpClient"),
        patch("clawdiney.query_engine.GraphDatabase.driver"),
        patch("clawdiney.query_engine.QueryCache"),
        patch("clawdiney.query_engine.Config.get_default_vault", return_value="general"),
        patch("clawdiney.query_engine.Config.VAULT_PATH", "~/test_vault"),
        patch("clawdiney.query_engine.Config.get_vault_path"),
        patch("clawdiney.query_engine.load_vault_config"),
    ):
        yield


@pytest.fixture
def mock_collections(mock_deps):
    collections = {}

    def get_collection(name):
        if name in collections:
            return collections[name]
        if name == "vault_general":
            coll = MagicMock()
            coll.query.return_value = {"documents": [[]], "metadatas": [[]]}
            collections[name] = coll
            return coll
        raise Exception(f"Collection {name} not found")

    chroma_client = MagicMock()
    chroma_client.get_collection.side_effect = get_collection

    cache_mock = MagicMock()
    cache_mock.get.return_value = None

    with (
        patch("clawdiney.query_engine.chromadb.HttpClient", return_value=chroma_client),
        patch("clawdiney.query_engine.QueryCache", return_value=cache_mock),
    ):
        engine = BrainQueryEngine()
        engine.get_embedding = MagicMock(return_value=[0.1, 0.2, 0.3])
        yield engine, collections


class TestBrainQueryEngineInit:
    def test_no_vault_uses_default(self, mock_deps):
        with patch("clawdiney.query_engine.chromadb.HttpClient"):
            engine = BrainQueryEngine()
        assert engine.current_vault == "general"

    def test_with_vault_param(self, mock_deps):
        with patch("clawdiney.query_engine.chromadb.HttpClient"):
            engine = BrainQueryEngine(vault="design")
        assert engine.current_vault == "design"

    def test_legacy_fallback_collection(self, mock_deps):
        chroma_client = MagicMock()
        chroma_client.get_collection.side_effect = [Exception("not found"), MagicMock()]
        with patch("clawdiney.query_engine.chromadb.HttpClient", return_value=chroma_client):
            engine = BrainQueryEngine(vault="nonexistent")
        assert engine.vector_collection is not None


class TestGetFallbackChain:
    def test_basic_chain(self, mock_collections):
        engine, _ = mock_collections
        engine.vault_config = None
        chain = engine._get_fallback_chain()
        assert chain == ["general"]

    def test_with_linked_vaults(self, mock_collections):
        engine, _ = mock_collections
        engine.current_vault = "design"
        engine.vault_config = MagicMock()
        engine.vault_config.linked_vaults = ["backend", "frontend"]
        chain = engine._get_fallback_chain()
        assert chain == ["design", "backend", "frontend", "general"]

    def test_general_not_duplicated(self, mock_collections):
        engine, _ = mock_collections
        engine.current_vault = "general"
        engine.vault_config = MagicMock()
        engine.vault_config.linked_vaults = []
        chain = engine._get_fallback_chain()
        assert chain == ["general"]


class TestGetVaultCollection:
    def test_caches_collections(self, mock_collections):
        engine, collections = mock_collections
        mock_coll = MagicMock()
        collections["vault_design"] = mock_coll
        coll = engine._get_vault_collection("design")
        assert coll is mock_coll
        assert "_collection_cache" in dir(engine)
        assert engine._collection_cache["design"] is mock_coll
        coll2 = engine._get_vault_collection("design")
        assert coll2 is coll

    def test_none_for_missing(self, mock_collections):
        engine, _ = mock_collections
        result = engine._get_vault_collection("nonexistent")
        assert result is None


class TestResolveNoteVaultAware:
    def test_resolve_note_with_vault_param(self, mock_collections):
        engine, _ = mock_collections
        with (
            patch("clawdiney.query_engine.Config.get_vault_path", return_value="/fake/projects_vault"),
            patch("pathlib.Path.rglob") as mock_rglob,
        ):
            fake_path = MagicMock(spec=Path)
            fake_path.relative_to.return_value = Path("my_note.md")
            fake_path.name = "my_note.md"
            fake_path.__str__.return_value = "/fake/projects_vault/my_note.md"
            mock_rglob.return_value = [fake_path]

            result = engine.resolve_note("my_note", vault="projects")
            assert len(result) == 1
            assert result[0]["path"] == "my_note.md"

    def test_resolve_note_no_vault_uses_current(self, mock_collections):
        engine, _ = mock_collections
        with patch("pathlib.Path.rglob") as mock_rglob:
            fake_path = MagicMock(spec=Path)
            fake_path.relative_to.return_value = Path("general_note.md")
            fake_path.name = "general_note.md"
            mock_rglob.return_value = [fake_path]

            result = engine.resolve_note("general_note")
            assert len(result) == 1


class TestGetRelatedNotesVaultAware:
    def test_get_related_notes_with_vault_filter(self, mock_collections):
        engine, _ = mock_collections
        mock_session = MagicMock()
        mock_record = MagicMock()
        mock_record.__getitem__.side_effect = lambda k: "related_note.md" if k == "path" else ""
        mock_session.run.return_value = [mock_record]
        engine.neo4j_driver.session.return_value.__enter__.return_value = mock_session

        result = engine.get_related_notes("some_note")

        call_kwargs = mock_session.run.call_args[1]
        assert "vault" in call_kwargs
        assert call_kwargs["vault"] == "general"
        assert "related_note.md" in result

    def test_get_related_notes_vault_param(self, mock_collections):
        engine, _ = mock_collections
        mock_session = MagicMock()
        mock_record = MagicMock()
        mock_record.__getitem__.side_effect = lambda k: "related.md" if k == "path" else ""
        mock_session.run.return_value = [mock_record]
        engine.neo4j_driver.session.return_value.__enter__.return_value = mock_session

        result = engine.get_related_notes("some_note", vault="design")

        call_kwargs = mock_session.run.call_args[1]
        assert call_kwargs["vault"] == "design"
        assert "related.md" in result


class TestGetNoteByPathVaultAware:
    def test_get_note_by_path_with_vault(self, mock_collections):
        engine, _ = mock_collections
        with (
            patch("clawdiney.query_engine.Config.get_vault_path", return_value="/fake/projects_vault"),
            patch("pathlib.Path.is_file", return_value=True),
            patch("pathlib.Path.read_text", return_value="# Note content"),
        ):
            result = engine.get_note_by_path("note.md", vault="projects")
            assert result["filename"] == "note.md"
            assert result["content"] == "# Note content"

    def test_get_note_by_path_no_vault(self, mock_collections):
        engine, _ = mock_collections
        engine.vault_root = Path("/fake/general_vault")
        with (
            patch("pathlib.Path.is_file", return_value=True),
            patch("pathlib.Path.read_text", return_value="# General"),
        ):
            result = engine.get_note_by_path("note.md")
            assert result["content"] == "# General"


class TestQueryWithVault:
    def test_cache_key_includes_vault(self, mock_collections):
        engine, collections = mock_collections
        engine.cache.get = MagicMock(return_value=None)
        engine.cache.set = MagicMock()
        engine.get_embedding = MagicMock(return_value=[0.1, 0.2, 0.3])
        collections["vault_general"].query.return_value = {
            "documents": [["doc1"]],
            "metadatas": [[{"path": "note1.md", "filename": "note1.md"}]],
        }
        engine.query("test query")
        cache_set_call = engine.cache.set.call_args
        assert cache_set_call is not None
        cache_key = cache_set_call[0][0]
        assert cache_key.startswith("general:")

    def test_fallback_chain_fills_results(self, mock_collections):
        engine, collections = mock_collections
        engine.current_vault = "design"
        engine.vault_config = MagicMock()
        engine.vault_config.linked_vaults = ["backend"]
        engine.get_embedding = MagicMock(return_value=[0.1, 0.2, 0.3])

        collections["vault_design"] = MagicMock()
        collections["vault_design"].query.return_value = {
            "documents": [["design_doc1"]],
            "metadatas": [[{"path": "design/note1.md", "filename": "note1.md"}]],
        }
        collections["vault_backend"] = MagicMock()
        collections["vault_backend"].query.return_value = {
            "documents": [["backend_doc1"]],
            "metadatas": [[{"path": "backend/note1.md", "filename": "note1.md"}]],
        }
        collections["vault_general"] = MagicMock()
        collections["vault_general"].query.return_value = {
            "documents": [["general_doc1"]],
            "metadatas": [[{"path": "general/note1.md", "filename": "note1.md"}]],
        }

        result = engine.query("test", n_results=3)
        assert "Source [design]" in result or "design/note1" in result
        assert "Source [backend]" in result or "backend/note1" in result
        assert "Source [general]" in result or "general/note1" in result

    def test_vault_override(self, mock_collections):
        engine, collections = mock_collections
        engine.current_vault = "design"
        engine.vault_config = MagicMock()
        engine.vault_config.linked_vaults = []
        engine.get_embedding = MagicMock(return_value=[0.1, 0.2, 0.3])

        collections["vault_frontend"] = MagicMock()
        collections["vault_frontend"].query.return_value = {
            "documents": [["frontend_doc1"]],
            "metadatas": [[{"path": "frontend/note1.md", "filename": "note1.md"}]],
        }
        collections["vault_general"].query.return_value = {
            "documents": [["general_doc1"]],
            "metadatas": [[{"path": "general/note1.md", "filename": "note1.md"}]],
        }

        result = engine.query("test", vault_override="frontend")
        assert "frontend" in result
