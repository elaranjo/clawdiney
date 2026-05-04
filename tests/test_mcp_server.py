import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def reset_globals():
    """Reset global state in mcp_server between tests."""
    import clawdiney.mcp_server as mcp_server

    with mcp_server._engine_lock:
        mcp_server._engine_instances.clear()
        mcp_server._auto_sync_started = False
    mcp_server._auto_sync_completed.clear()
    yield


@pytest.fixture
def mock_engine():
    engine = MagicMock()
    engine.current_vault = "default"
    engine.query.return_value = "Mocked search results"
    engine.get_related_notes.return_value = ["related-note-1.md"]
    engine.resolve_note.return_value = [
        {"path": "some/note.md", "filename": "note.md", "score": 0}
    ]
    engine.get_note_chunks.return_value = [
        {"path": "some/note.md", "chunk_index": 0, "header": "# Title"}
    ]
    return engine


@pytest.fixture
def mock_writer():
    writer = MagicMock()
    writer.write_note.return_value = {
        "success": True,
        "path": "test.md",
        "message": "Note written and indexed: test.md",
        "chunks_indexed": 3,
    }
    writer.append_to_daily.return_value = {
        "success": True,
        "path": "50_Daily/2024-01-01.md",
        "message": "Content appended to daily note",
        "chunks_indexed": 1,
    }
    writer.delete_note.return_value = {
        "success": True,
        "path": "test.md",
        "message": "Note deleted: test.md",
        "chunks_indexed": None,
    }
    return writer


@patch("clawdiney.mcp_server.get_engine")
@patch("clawdiney.mcp_server._ensure_auto_sync")
class TestSearchTools:
    def test_search_brain_no_vault(self, mock_sync, mock_get_engine, mock_engine):
        mock_get_engine.return_value = mock_engine
        from clawdiney.mcp_server import search_brain

        result = search_brain(query="test query")
        assert "Mocked search results" in result
        mock_get_engine.assert_called_once_with(vault=None)

    def test_search_brain_with_vault(self, mock_sync, mock_get_engine, mock_engine):
        mock_get_engine.return_value = mock_engine
        from clawdiney.mcp_server import search_brain

        result = search_brain(query="test query", vault="projects")
        assert "Mocked search results" in result
        mock_get_engine.assert_called_once_with(vault="projects")

    def test_explore_graph_no_vault(self, mock_sync, mock_get_engine, mock_engine):
        mock_get_engine.return_value = mock_engine
        from clawdiney.mcp_server import explore_graph

        result = explore_graph(note_name="test-note")
        assert "related-note-1.md" in result
        mock_get_engine.assert_called_once_with(vault=None)

    def test_explore_graph_with_vault(self, mock_sync, mock_get_engine, mock_engine):
        mock_get_engine.return_value = mock_engine
        from clawdiney.mcp_server import explore_graph

        result = explore_graph(note_name="test-note", vault="projects")
        assert "related-note-1.md" in result
        mock_get_engine.assert_called_once_with(vault="projects")

    def test_resolve_note_no_vault(self, mock_sync, mock_get_engine, mock_engine):
        mock_get_engine.return_value = mock_engine
        from clawdiney.mcp_server import resolve_note

        result = resolve_note(name="note")
        assert "some/note.md" in result
        mock_get_engine.assert_called_once_with(vault=None)

    def test_resolve_note_with_vault(self, mock_sync, mock_get_engine, mock_engine):
        mock_get_engine.return_value = mock_engine
        from clawdiney.mcp_server import resolve_note

        result = resolve_note(name="note", vault="projects")
        assert "some/note.md" in result
        mock_get_engine.assert_called_once_with(vault="projects")

    def test_get_note_chunks_no_vault(self, mock_sync, mock_get_engine, mock_engine):
        mock_get_engine.return_value = mock_engine
        from clawdiney.mcp_server import get_note_chunks

        result = get_note_chunks(filename="note.md")
        assert "# Title" in result
        mock_get_engine.assert_called_once_with(vault=None)

    def test_get_note_chunks_with_vault(self, mock_sync, mock_get_engine, mock_engine):
        mock_get_engine.return_value = mock_engine
        from clawdiney.mcp_server import get_note_chunks

        result = get_note_chunks(filename="note.md", vault="projects")
        assert "# Title" in result
        mock_get_engine.assert_called_once_with(vault="projects")


@patch("clawdiney.mcp_server.get_engine")
@patch("clawdiney.mcp_server._ensure_auto_sync")
@patch("clawdiney.vault_writer.get_writer")
class TestWriteTools:
    def test_write_note_no_vault(self, mock_get_writer, mock_sync, mock_get_engine, mock_engine, mock_writer):
        mock_get_engine.return_value = mock_engine
        mock_get_writer.return_value = mock_writer
        from clawdiney.mcp_server import write_note

        result = write_note(path="test.md", content="# Test")
        assert "Indexed 3 chunks" in result
        mock_get_writer.assert_called_once_with(vault_name=None)

    def test_write_note_with_vault(self, mock_get_writer, mock_sync, mock_get_engine, mock_engine, mock_writer):
        mock_get_engine.return_value = mock_engine
        mock_get_writer.return_value = mock_writer
        from clawdiney.mcp_server import write_note

        result = write_note(path="test.md", content="# Test", vault="projects")
        assert "Indexed 3 chunks" in result
        mock_get_writer.assert_called_once_with(vault_name="projects")

    def test_append_to_daily_no_vault(self, mock_get_writer, mock_sync, mock_get_engine, mock_engine, mock_writer):
        mock_get_engine.return_value = mock_engine
        mock_get_writer.return_value = mock_writer
        from clawdiney.mcp_server import append_to_daily

        result = append_to_daily(content="## Learnings")
        assert "daily note" in result
        mock_get_writer.assert_called_once_with(vault_name=None)

    def test_append_to_daily_with_vault(self, mock_get_writer, mock_sync, mock_get_engine, mock_engine, mock_writer):
        mock_get_engine.return_value = mock_engine
        mock_get_writer.return_value = mock_writer
        from clawdiney.mcp_server import append_to_daily

        result = append_to_daily(content="## Learnings", vault="personal")
        assert "daily note" in result
        mock_get_writer.assert_called_once_with(vault_name="personal")

    def test_add_learning_no_vault(self, mock_get_writer, mock_sync, mock_get_engine, mock_engine, mock_writer):
        mock_get_engine.return_value = mock_engine
        mock_get_writer.return_value = mock_writer
        from clawdiney.mcp_server import add_learning

        result = add_learning(topic="TestTopic", content="# Content")
        assert "Learning saved" in result
        mock_get_writer.assert_called_once_with(vault_name=None)

    def test_add_learning_with_vault(self, mock_get_writer, mock_sync, mock_get_engine, mock_engine, mock_writer):
        mock_get_engine.return_value = mock_engine
        mock_get_writer.return_value = mock_writer
        from clawdiney.mcp_server import add_learning

        result = add_learning(topic="TestTopic", content="# Content", vault="projects")
        assert "Learning saved" in result
        mock_get_writer.assert_called_once_with(vault_name="projects")

    def test_delete_note_no_vault(self, mock_get_writer, mock_sync, mock_get_engine, mock_engine, mock_writer):
        mock_get_engine.return_value = mock_engine
        mock_get_writer.return_value = mock_writer
        from clawdiney.mcp_server import delete_note

        result = delete_note(path="test.md")
        assert "Note deleted" in result
        mock_get_writer.assert_called_once_with(vault_name=None)

    def test_delete_note_with_vault(self, mock_get_writer, mock_sync, mock_get_engine, mock_engine, mock_writer):
        mock_get_engine.return_value = mock_engine
        mock_get_writer.return_value = mock_writer
        from clawdiney.mcp_server import delete_note

        result = delete_note(path="test.md", vault="projects")
        assert "Note deleted" in result
        mock_get_writer.assert_called_once_with(vault_name="projects")


@patch("clawdiney.mcp_server.Config.get_all_vaults")
@patch("clawdiney.mcp_server._engine_instances", {"default": MagicMock(), "projects": MagicMock()})
class TestHealthCheck:
    def test_health_check_shows_vaults(self, mock_get_all_vaults):
        mock_get_all_vaults.return_value = {
            "default": Path("/vaults/default"),
            "projects": Path("/vaults/projects"),
        }
        from clawdiney.mcp_server import health_check

        result = health_check()
        assert "default" in result
        assert "projects" in result
