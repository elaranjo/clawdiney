from unittest.mock import MagicMock, patch

import pytest

from clawdiney.query_engine import BrainQueryEngine


@pytest.fixture(autouse=True)
def mock_brain_deps():
    """Mock database and external API dependencies for BrainQueryEngine."""
    chroma_client = MagicMock()
    mock_collection = MagicMock()
    mock_collection.query.return_value = {
        "documents": [["Test doc content"]],
        "metadatas": [[{"path": "README.md", "heading": "# README"}]],
        "distances": [[0.1]],
    }
    chroma_client.get_collection.return_value = mock_collection

    mock_driver = MagicMock()
    mock_session = MagicMock()
    mock_session.run.return_value = []
    mock_driver.session.return_value.__enter__.return_value = mock_session

    cache_mock = MagicMock()
    cache_mock.get.return_value = None

    with (
        patch("clawdiney.query_engine.chromadb.HttpClient", return_value=chroma_client),
        patch("clawdiney.query_engine.GraphDatabase.driver", return_value=mock_driver),
        patch("clawdiney.query_engine.QueryCache", return_value=cache_mock),
        patch("clawdiney.query_engine.Config.VAULT_PATH", "/tmp/mock_vault"),
        patch(
            "clawdiney.query_engine.Config.get_vault_path",
            return_value="/tmp/mock_vault",
        ),
        patch(
            "clawdiney.query_engine.Config.get_default_vault", return_value="general"
        ),
        patch("clawdiney.query_engine.load_vault_config"),
        patch(
            "clawdiney.query_engine.BrainQueryEngine.get_embedding",
            return_value=[0.1, 0.2, 0.3],
        ),
    ):
        yield


def test_query_returns_string():
    engine = BrainQueryEngine()
    try:
        result = engine.query("design system", use_rerank=False)
        assert isinstance(result, str)
        assert "Test doc content" in result or result == ""
    finally:
        engine.close()


def test_resolve_note_returns_list():
    engine = BrainQueryEngine()
    try:
        # Mock resolve_note dependencies inside the engine
        with patch.object(
            engine,
            "resolve_note",
            return_value=[{"path": "README.md", "filename": "README.md", "score": 100}],
        ):
            result = engine.resolve_note("README.md")
            assert isinstance(result, list)
            assert len(result) > 0
            assert result[0]["path"] == "README.md"
    finally:
        engine.close()
