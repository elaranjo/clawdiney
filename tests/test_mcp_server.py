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
    engine.retrieve.return_value = [
        {"path": "some/note.md", "vault": "default", "content": "body"}
    ]
    engine.build_context.return_value = "Mocked search results"
    engine.get_conflicts_for_rows.return_value = []
    engine.get_related_notes.return_value = ["related-note-1.md"]
    engine.storage.get_conflicts.return_value = []
    engine.storage.expand_neighborhood.return_value = [
        {
            "name": "related-note-1.md",
            "path": "related-note-1.md",
            "kind": "note",
            "rel_type": "LINKS_TO",
            "confidence": 1.0,
            "evidence": None,
            "distance": 1,
        }
    ]
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

    def test_search_brain_default_n_results_unchanged(
        self, mock_sync, mock_get_engine, mock_engine
    ):
        mock_get_engine.return_value = mock_engine
        from clawdiney.constants import SEARCH_N_RESULTS_DEFAULT
        from clawdiney.mcp_server import search_brain

        search_brain(query="test query")
        mock_engine.retrieve.assert_called_once_with(
            "test query",
            vault_override=None,
            agent_id=None,
            n_results=SEARCH_N_RESULTS_DEFAULT,
        )

    def test_search_brain_explicit_n_results_respected(
        self, mock_sync, mock_get_engine, mock_engine
    ):
        mock_get_engine.return_value = mock_engine
        from clawdiney.mcp_server import search_brain

        search_brain(query="test query", n_results=10)
        mock_engine.retrieve.assert_called_once_with(
            "test query", vault_override=None, agent_id=None, n_results=10
        )

    def test_search_brain_zero_skips_retrieval(
        self, mock_sync, mock_get_engine, mock_engine
    ):
        mock_get_engine.return_value = mock_engine
        from clawdiney.mcp_server import search_brain

        result = search_brain(query="test query", n_results=0)
        mock_get_engine.assert_not_called()
        assert "0 results requested" in result
        assert "no search performed" in result

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

    def test_search_brain_surfaces_conflicts(
        self, mock_sync, mock_get_engine, mock_engine
    ):
        mock_get_engine.return_value = mock_engine
        mock_engine.get_conflicts_for_rows.return_value = [
            {
                "source": "proj",
                "rel_type": "USES_PATTERN",
                "target": "old-lib",
                "confidence": 0.6,
                "relation_id": 1,
            },
            {
                "source": "proj",
                "rel_type": "USES_PATTERN",
                "target": "new-lib",
                "confidence": 0.7,
                "relation_id": 2,
            },
        ]
        from clawdiney.mcp_server import search_brain

        result = search_brain(query="test query")
        assert "Unresolved conflicts" in result
        assert "old-lib" in result and "new-lib" in result

    def test_search_brain_no_conflicts_no_section(
        self, mock_sync, mock_get_engine, mock_engine
    ):
        mock_get_engine.return_value = mock_engine
        from clawdiney.mcp_server import search_brain

        result = search_brain(query="test query")
        assert "Unresolved conflicts" not in result

    def test_explore_graph_surfaces_conflicts(
        self, mock_sync, mock_get_engine, mock_engine
    ):
        mock_get_engine.return_value = mock_engine
        mock_engine.storage.get_conflicts.return_value = [
            {
                "source": "proj",
                "rel_type": "USES_PATTERN",
                "target": "old-lib",
                "confidence": 0.6,
                "relation_id": 1,
            }
        ]
        from clawdiney.mcp_server import explore_graph

        result = explore_graph(note_name="proj")
        assert "Unresolved conflicts" in result
        assert "old-lib" in result

    def test_explore_graph_no_conflicts_no_section(
        self, mock_sync, mock_get_engine, mock_engine
    ):
        mock_get_engine.return_value = mock_engine
        from clawdiney.mcp_server import explore_graph

        result = explore_graph(note_name="test-note")
        assert "Unresolved conflicts" not in result

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
    def test_write_note_no_vault(
        self, mock_get_writer, mock_sync, mock_get_engine, mock_engine, mock_writer
    ):
        mock_get_engine.return_value = mock_engine
        mock_get_writer.return_value = mock_writer
        from clawdiney.mcp_server import write_note

        result = write_note(path="test.md", content="# Test")
        assert "Indexed 3 chunks" in result
        mock_get_writer.assert_called_once_with(vault_name=None)

    def test_write_note_with_vault(
        self, mock_get_writer, mock_sync, mock_get_engine, mock_engine, mock_writer
    ):
        mock_get_engine.return_value = mock_engine
        mock_get_writer.return_value = mock_writer
        from clawdiney.mcp_server import write_note

        result = write_note(path="test.md", content="# Test", vault="projects")
        assert "Indexed 3 chunks" in result
        mock_get_writer.assert_called_once_with(vault_name="projects")

    def test_append_to_daily_no_vault(
        self, mock_get_writer, mock_sync, mock_get_engine, mock_engine, mock_writer
    ):
        mock_get_engine.return_value = mock_engine
        mock_get_writer.return_value = mock_writer
        from clawdiney.mcp_server import append_to_daily

        result = append_to_daily(content="## Learnings")
        assert "daily note" in result
        mock_get_writer.assert_called_once_with(vault_name=None)

    def test_append_to_daily_with_vault(
        self, mock_get_writer, mock_sync, mock_get_engine, mock_engine, mock_writer
    ):
        mock_get_engine.return_value = mock_engine
        mock_get_writer.return_value = mock_writer
        from clawdiney.mcp_server import append_to_daily

        result = append_to_daily(content="## Learnings", vault="personal")
        assert "daily note" in result
        mock_get_writer.assert_called_once_with(vault_name="personal")

    def test_add_learning_no_vault(
        self, mock_get_writer, mock_sync, mock_get_engine, mock_engine, mock_writer
    ):
        mock_get_engine.return_value = mock_engine
        mock_get_writer.return_value = mock_writer
        from clawdiney.mcp_server import add_learning

        result = add_learning(topic="TestTopic", content="# Content")
        assert "Learning saved" in result
        mock_get_writer.assert_called_once_with(vault_name=None)

    def test_add_learning_with_vault(
        self, mock_get_writer, mock_sync, mock_get_engine, mock_engine, mock_writer
    ):
        mock_get_engine.return_value = mock_engine
        mock_get_writer.return_value = mock_writer
        from clawdiney.mcp_server import add_learning

        result = add_learning(topic="TestTopic", content="# Content", vault="projects")
        assert "Learning saved" in result
        mock_get_writer.assert_called_once_with(vault_name="projects")

    def test_delete_note_no_vault(
        self, mock_get_writer, mock_sync, mock_get_engine, mock_engine, mock_writer
    ):
        mock_get_engine.return_value = mock_engine
        mock_get_writer.return_value = mock_writer
        from clawdiney.mcp_server import delete_note

        result = delete_note(path="test.md")
        assert "Note deleted" in result
        mock_get_writer.assert_called_once_with(vault_name=None)

    def test_delete_note_with_vault(
        self, mock_get_writer, mock_sync, mock_get_engine, mock_engine, mock_writer
    ):
        mock_get_engine.return_value = mock_engine
        mock_get_writer.return_value = mock_writer
        from clawdiney.mcp_server import delete_note

        result = delete_note(path="test.md", vault="projects")
        assert "Note deleted" in result
        mock_get_writer.assert_called_once_with(vault_name="projects")


@patch("clawdiney.mcp_server.Config.get_all_vaults")
@patch(
    "clawdiney.mcp_server._engine_instances",
    {"default": MagicMock(), "projects": MagicMock()},
)
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


class TestProjectGraphTools:
    @pytest.fixture()
    def graph_engine(self, tmp_path):
        """Engine-like mock backed by a real BrainStorage with a project graph."""
        from clawdiney.storage import BrainStorage

        storage = BrainStorage(db_path=tmp_path / "brain.db", dimension=4)
        storage.upsert_typed_entity("default", "proj-a", "project")
        storage.upsert_typed_entity("default", "proj-b", "project")
        lib = storage.upsert_typed_entity("default", "shared-lib", "library")
        storage.replace_project_relations(
            "default",
            "proj-a",
            "deterministic",
            [{"target_id": lib, "rel_type": "DEPENDS_ON", "confidence": 1.0}],
        )
        storage.replace_project_relations(
            "default",
            "proj-b",
            "deterministic",
            [{"target_id": lib, "rel_type": "DEPENDS_ON", "confidence": 1.0}],
        )
        storage.upsert_typed_entity("default", "island", "project")

        engine = MagicMock()
        engine.current_vault = "default"
        engine.storage = storage
        yield engine
        storage.close()

    def test_relate_shared_library(self, graph_engine):
        import clawdiney.mcp_server as mcp_server

        with (
            patch.object(mcp_server, "get_engine", return_value=graph_engine),
            patch.object(mcp_server, "_ensure_auto_sync"),
        ):
            result = mcp_server.how_do_projects_relate("proj-a", "proj-b")
        assert "DEPENDS_ON" in result
        assert "shared-lib" in result

    def test_relate_no_path(self, graph_engine):
        import clawdiney.mcp_server as mcp_server

        with (
            patch.object(mcp_server, "get_engine", return_value=graph_engine),
            patch.object(mcp_server, "_ensure_auto_sync"),
        ):
            result = mcp_server.how_do_projects_relate("proj-a", "island")
        assert "No relationship found" in result

    def test_relate_unknown_project_names_argument(self, graph_engine):
        import clawdiney.mcp_server as mcp_server

        with (
            patch.object(mcp_server, "get_engine", return_value=graph_engine),
            patch.object(mcp_server, "_ensure_auto_sync"),
        ):
            result = mcp_server.how_do_projects_relate("proj-a", "ghost")
        assert "project_b" in result and "ghost" in result

    def test_explore_graph_typed_output(self, graph_engine):
        import clawdiney.mcp_server as mcp_server

        with (
            patch.object(mcp_server, "get_engine", return_value=graph_engine),
            patch.object(mcp_server, "_ensure_auto_sync"),
        ):
            result = mcp_server.explore_graph("proj-a")
        assert "shared-lib [library] via DEPENDS_ON" in result

    def test_get_project_card_exact(self, mock_engine):
        import clawdiney.mcp_server as mcp_server

        mock_engine.resolve_note.return_value = [
            {
                "path": "00_Inbox/Projetos/clawdiney.md",
                "filename": "clawdiney.md",
                "score": 0,
            }
        ]
        mock_engine.get_note_by_path.return_value = {
            "path": "00_Inbox/Projetos/clawdiney.md",
            "filename": "clawdiney.md",
            "content": "# clawdiney\n\n## Purpose\nBrain.",
        }
        with (
            patch.object(mcp_server, "get_engine", return_value=mock_engine),
            patch.object(mcp_server, "_ensure_auto_sync"),
        ):
            result = mcp_server.get_project_card("clawdiney")
        assert "## Purpose" in result

    def test_get_project_card_unknown_lists_candidates(self, mock_engine):
        import clawdiney.mcp_server as mcp_server

        mock_engine.resolve_note.return_value = []
        with (
            patch.object(mcp_server, "get_engine", return_value=mock_engine),
            patch.object(mcp_server, "_ensure_auto_sync"),
        ):
            result = mcp_server.get_project_card("ghost")
        assert "No project card found" in result

    def test_get_project_card_ambiguous(self, mock_engine):
        import clawdiney.mcp_server as mcp_server

        mock_engine.resolve_note.return_value = [
            {"path": "a/demo-api.md", "filename": "demo-api.md", "score": 2},
            {"path": "b/demo-web.md", "filename": "demo-web.md", "score": 2},
        ]
        with (
            patch.object(mcp_server, "get_engine", return_value=mock_engine),
            patch.object(mcp_server, "_ensure_auto_sync"),
        ):
            result = mcp_server.get_project_card("demo")
        assert "Closest candidates" in result
        assert "demo-api.md" in result
