"""A local end-to-end path through indexing, retrieval, graph, and MCP tools."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from clawdiney.indexer import index_vault
from clawdiney.query_engine import BrainQueryEngine
from clawdiney.storage import BrainStorage, SchemaMismatchError


def _vector(text):
    # Deterministic fake API response; no note content leaves the test process.
    return [float(len(text) % 11 + 1), 0.5, 0.25, 0.125]


def test_openai_mode_indexes_searches_and_explores_without_ollama(
    tmp_path, monkeypatch
):
    from clawdiney import mcp_server

    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Architecture.md").write_text(
        "# Architecture\n\nUse the repository pattern. [[Deployment]] #backend",
        encoding="utf-8",
    )
    (vault / "Deployment.md").write_text(
        "# Deployment\n\nDeploy the backend after tests pass.", encoding="utf-8"
    )
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("VAULTS", raising=False)
    monkeypatch.delenv("VAULTS_DIR", raising=False)
    monkeypatch.setattr("clawdiney.config.Config.EMBEDDING_PROVIDER", "openai")
    monkeypatch.setattr("clawdiney.config.Config.MODEL_NAME", "text-embedding-3-small")
    monkeypatch.setattr("clawdiney.config.Config.EMBEDDING_DIMENSION", 4)
    monkeypatch.setattr("clawdiney.config.Config.VAULT_PATH", str(vault))
    monkeypatch.setattr("clawdiney.config.Config.ENABLE_RERANK", False)

    client = MagicMock()

    def create(*, model, input):
        assert model == "text-embedding-3-small"
        texts = [input] if isinstance(input, str) else input
        return SimpleNamespace(
            data=[
                SimpleNamespace(index=i, embedding=_vector(text))
                for i, text in enumerate(texts)
            ]
        )

    client.embeddings.create.side_effect = create
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=lambda: client))
    storage = BrainStorage(tmp_path / "openai.db")
    try:
        with patch("ollama.Client", side_effect=AssertionError("Ollama was contacted")):
            summary = index_vault(vault_root=vault, storage=storage)
            assert summary["indexed_chunks"] >= 2
            engine = BrainQueryEngine(storage=storage)
            monkeypatch.setattr(mcp_server, "get_engine", lambda vault=None: engine)
            monkeypatch.setattr("clawdiney.storage.get_storage", lambda: storage)
            monkeypatch.setattr(
                "clawdiney.config.Config.get_all_vaults", lambda: {"default": vault}
            )
            search = mcp_server.search_brain("repository pattern")
            graph = mcp_server.explore_graph("Architecture.md")
            health = mcp_server.health_check()

        assert "Architecture.md" in search
        assert "Deployment.md" in graph
        assert "All services healthy" in health
        assert "Embeddings (openai, text-embedding-3-small): OK" in health
        assert client.embeddings.create.call_count >= 3
    finally:
        storage.close()


def test_invalid_vault_does_not_create_database(tmp_path, monkeypatch):
    db = tmp_path / "brain.db"
    monkeypatch.setattr("clawdiney.config.Config.BRAIN_DB_PATH", str(db))
    with pytest.raises(FileNotFoundError, match="Vault directory does not exist"):
        index_vault(vault_root=tmp_path / "missing")
    assert not db.exists()


def test_missing_openai_key_does_not_create_database(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "Note.md").write_text("# Note\n", encoding="utf-8")
    db = tmp_path / "brain.db"
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr("clawdiney.config.Config.EMBEDDING_PROVIDER", "openai")
    monkeypatch.setattr("clawdiney.config.Config.BRAIN_DB_PATH", str(db))

    with pytest.raises(ValueError, match="OPENAI_API_KEY"):
        index_vault(vault_root=vault)

    assert not db.exists()


def test_switching_to_openai_dimension_preserves_old_database(tmp_path, monkeypatch):
    db = tmp_path / "existing.db"
    BrainStorage(db_path=db, dimension=1024).close()
    monkeypatch.setattr("clawdiney.config.Config.MODEL_NAME", "text-embedding-3-small")
    with pytest.raises(SchemaMismatchError, match="back up"):
        BrainStorage(db_path=db, dimension=1536)
    assert db.exists()
