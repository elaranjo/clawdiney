import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.original_chroma_host = os.environ.get("CHROMA_HOST")
        self.original_chroma_port = os.environ.get("CHROMA_PORT")

        os.environ.pop("CHROMA_HOST", None)
        os.environ.pop("CHROMA_PORT", None)

    def tearDown(self):
        if self.original_chroma_host is not None:
            os.environ["CHROMA_HOST"] = self.original_chroma_host
        else:
            os.environ.pop("CHROMA_HOST", None)

        if self.original_chroma_port is not None:
            os.environ["CHROMA_PORT"] = self.original_chroma_port
        else:
            os.environ.pop("CHROMA_PORT", None)

    def test_http_chroma_config(self):
        os.environ["CHROMA_HOST"] = "test-host"
        os.environ["CHROMA_PORT"] = "8080"

        from config import Config

        self.assertEqual(
            Config.get_chroma_client_config(), {"host": "test-host", "port": 8080}
        )


class BrainQueryEngineUnitTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.temp_dir, "frontend"), exist_ok=True)
        os.makedirs(os.path.join(self.temp_dir, "backend"), exist_ok=True)

        with open(
            os.path.join(self.temp_dir, "frontend", "design.md"), "w", encoding="utf-8"
        ) as file:
            file.write("# Frontend Design\n\n## Tokens\nButton tokens.\n")

        with open(
            os.path.join(self.temp_dir, "backend", "design.md"), "w", encoding="utf-8"
        ) as file:
            file.write("# Backend Design\n\n## Contracts\nAPI contracts.\n")

        with open(
            os.path.join(self.temp_dir, "frontend", "guide.md"), "w", encoding="utf-8"
        ) as file:
            file.write("# Guide\n\nUseful notes.\n")

        self.config_patch = patch("query_engine.Config")
        self.mock_config = self.config_patch.start()
        self.mock_config.VAULT_PATH = self.temp_dir
        self.mock_config.NEO4J_URI = "bolt://test"
        self.mock_config.NEO4J_USER = "neo4j"
        self.mock_config.NEO4J_PASSWORD = "secret"
        self.mock_config.MODEL_NAME = "bge-m3:latest"
        self.mock_config.RERANK_MODEL_NAME = "rerank-model"
        self.mock_config.RERANK_THRESHOLD = "0.5"
        self.mock_config.get_chroma_client_config.return_value = {
            "host": "localhost",
            "port": 8000,
        }

        self.chroma_patch = patch("query_engine.chromadb.HttpClient")
        self.neo4j_patch = patch("query_engine.GraphDatabase.driver")

        self.mock_http_client = self.chroma_patch.start()
        self.mock_driver_factory = self.neo4j_patch.start()

        self.mock_collection = MagicMock()
        self.mock_http_client.return_value.get_collection.return_value = (
            self.mock_collection
        )

        self.mock_driver = MagicMock()
        self.mock_driver_factory.return_value = self.mock_driver

        from query_engine import BrainQueryEngine

        self.engine = BrainQueryEngine()

    def tearDown(self):
        self.engine.close()
        self.chroma_patch.stop()
        self.neo4j_patch.stop()
        self.config_patch.stop()
        shutil.rmtree(self.temp_dir)

    def test_resolve_note_returns_canonical_candidates(self):
        candidates = self.engine.resolve_note("design.md")

        self.assertEqual(
            [candidate["path"] for candidate in candidates],
            ["backend/design.md", "frontend/design.md"],
        )

    def test_get_note_by_path_reads_canonical_path(self):
        note = self.engine.get_note_by_path("frontend/design.md")

        self.assertEqual(note["path"], "frontend/design.md")
        self.assertEqual(note["filename"], "design.md")
        self.assertIn("Frontend Design", note["content"])

    def test_get_note_by_path_rejects_outside_vault(self):
        with self.assertRaises(ValueError):
            self.engine.get_note_by_path("../outside.md")

    def test_get_note_chunks_requires_disambiguation(self):
        with self.assertRaises(ValueError):
            self.engine.get_note_chunks("design.md")

    def test_get_note_chunks_returns_header_chunks_for_canonical_path(self):
        chunks = self.engine.get_note_chunks("frontend/design.md")

        self.assertEqual(chunks[0]["path"], "frontend/design.md")
        self.assertEqual(chunks[0]["header"], "Frontend Design")
        self.assertEqual(chunks[1]["header"], "Tokens")

    def test_rerank_results_falls_back_to_original_results_when_model_fails(self):
        results = [
            ("doc-1", {"filename": "guide.md"}),
            ("doc-2", {"filename": "design.md"}),
        ]

        with patch(
            "query_engine.ollama.generate", side_effect=RuntimeError("missing model")
        ):
            reranked = self.engine.rerank_results("design", results)

        self.assertEqual(reranked, results)

    def test_rerank_results_falls_back_when_no_score_passes_threshold(self):
        results = [
            ("doc-1", {"filename": "guide.md"}),
            ("doc-2", {"filename": "design.md"}),
        ]

        responses = [{"response": "0.1"}, {"response": "0.2"}]
        with patch("query_engine.ollama.generate", side_effect=responses):
            reranked = self.engine.rerank_results("design", results)

        self.assertEqual(reranked, results)


class BrainIndexerUnitTest(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.temp_dir, "frontend"), exist_ok=True)

        with open(
            os.path.join(self.temp_dir, "frontend", "design.md"), "w", encoding="utf-8"
        ) as file:
            file.write("# Frontend Design\n\n## Tokens\nButton tokens. #design #ui\n")

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_build_note_record_preserves_path_tags_and_chunks(self):
        from brain_indexer import build_note_record

        record = build_note_record(
            Path(os.path.join(self.temp_dir, "frontend", "design.md")),
            Path(self.temp_dir),
            strategy="headers",
        )

        self.assertEqual(record["path"], "frontend/design.md")
        self.assertEqual(record["tags"], ["design", "ui"])
        self.assertEqual(record["chunks"][0]["header"], "Frontend Design")
        self.assertEqual(record["chunks"][1]["header"], "Tokens")

    def test_index_vault_uses_injected_dependencies(self):
        from brain_indexer import index_vault

        fake_collection = MagicMock()
        fake_driver = MagicMock()

        summary = index_vault(
            vault_root=self.temp_dir,
            collection=fake_collection,
            neo4j_driver=fake_driver,
            strategy="headers",
        )

        self.assertEqual(summary["processed_files"], 1)
        self.assertEqual(summary["indexed_chunks"], 2)
        fake_collection.upsert.assert_called_once()
        fake_driver.session.assert_called_once()


class BrainMCPServerUnitTest(unittest.TestCase):
    def test_resolve_note_formats_candidates(self):
        fake_engine = MagicMock()
        fake_engine.resolve_note.return_value = [
            {"path": "backend/design.md", "filename": "design.md", "score": 0},
            {"path": "frontend/design.md", "filename": "design.md", "score": 1},
        ]

        with patch("brain_mcp_server.get_engine", return_value=fake_engine):
            from brain_mcp_server import resolve_note

            output = resolve_note("design.md")

        self.assertIn("Candidates for 'design.md':", output)
        self.assertIn("backend/design.md", output)
        self.assertIn("frontend/design.md", output)

    def test_get_note_chunks_formats_chunk_summary(self):
        fake_engine = MagicMock()
        fake_engine.get_note_chunks.return_value = [
            {
                "path": "frontend/design.md",
                "filename": "design.md",
                "header": "Frontend Design",
                "content": "Overview",
                "chunk_index": 0,
            },
            {
                "path": "frontend/design.md",
                "filename": "design.md",
                "header": "Tokens",
                "content": "Button tokens.",
                "chunk_index": 1,
            },
        ]

        with patch("brain_mcp_server.get_engine", return_value=fake_engine):
            from brain_mcp_server import get_note_chunks

            output = get_note_chunks("frontend/design.md")

        self.assertIn("Chunks for frontend/design.md:", output)
        self.assertIn("[0] Frontend Design", output)
        self.assertIn("[1] Tokens", output)


if __name__ == "__main__":
    unittest.main()
