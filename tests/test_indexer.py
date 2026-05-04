import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from clawdiney.indexer import (
    COLLECTION_PREFIX,
    NoteRecord,
    build_chunk_payload,
    create_collection,
    index_all_vaults,
    index_named_vault,
    index_vault,
    sync_graph,
)


class TestCreateCollection(unittest.TestCase):
    def setUp(self):
        self.client = MagicMock()
        self.collection_mock = MagicMock()
        self.client.get_or_create_collection.return_value = self.collection_mock

    def test_no_vault_name_uses_legacy_name(self):
        collection = create_collection(self.client)
        self.client.get_or_create_collection.assert_called_once()
        args, kwargs = self.client.get_or_create_collection.call_args
        self.assertEqual(kwargs["name"], "obsidian_vault")
        self.assertEqual(collection, self.collection_mock)

    def test_with_vault_name_uses_prefix(self):
        collection = create_collection(self.client, vault_name="general")
        self.client.get_or_create_collection.assert_called_once()
        args, kwargs = self.client.get_or_create_collection.call_args
        self.assertEqual(kwargs["name"], f"{COLLECTION_PREFIX}general")
        self.assertEqual(collection, self.collection_mock)

    def test_with_different_vault_name(self):
        collection = create_collection(self.client, vault_name="projects")
        args, kwargs = self.client.get_or_create_collection.call_args
        self.assertEqual(kwargs["name"], f"{COLLECTION_PREFIX}projects")


class TestBuildChunkPayload(unittest.TestCase):
    def setUp(self):
        self.note_record: NoteRecord = {
            "name": "test_note.md",
            "path": "subdir/test_note.md",
            "source": "/vault/subdir/test_note.md",
            "content": "# Header\n\nSome content here.",
            "tags": ["tag1", "tag2"],
            "wikilinks": [],
            "chunks": [
                {"header": "Header", "content": "Some content here.", "order": 0}
            ],
        }

    def test_no_vault_name_no_vault_in_metadata(self):
        ids, docs, metadatas = build_chunk_payload(self.note_record)
        self.assertNotIn("vault", metadatas[0])

    def test_with_vault_name_adds_vault_to_metadata(self):
        ids, docs, metadatas = build_chunk_payload(self.note_record, vault_name="general")
        self.assertIn("vault", metadatas[0])
        self.assertEqual(metadatas[0]["vault"], "general")

    def test_with_empty_vault_name_no_vault_in_metadata(self):
        ids, docs, metadatas = build_chunk_payload(self.note_record, vault_name="")
        self.assertNotIn("vault", metadatas[0])


class TestSyncGraphFullSyncScope(unittest.TestCase):
    def setUp(self):
        self.driver = MagicMock()
        self.session = MagicMock()
        self.session.__enter__.return_value = self.session
        self.tx = MagicMock()
        self.tx.__enter__.return_value = self.tx
        self.session.begin_transaction.return_value = self.tx
        self.driver.session.return_value = self.session

        self.note_records: list[NoteRecord] = [
            {
                "name": "note1.md",
                "path": "note1.md",
                "source": "/vault/note1.md",
                "content": "Content 1",
                "tags": ["tag-a"],
                "wikilinks": [],
                "chunks": [{"header": "", "content": "Content 1", "order": 0}],
            }
        ]

    def _get_delete_call(self, vault_name: str) -> str | None:
        sync_graph(self.driver, self.note_records, vault_name=vault_name)
        tx_run = self.tx.run
        for call_args in tx_run.call_args_list:
            cypher = call_args[0][0]
            if "DELETE r" in cypher and "Tag" not in cypher:
                return cypher
        return None

    def test_full_sync_vault_a_does_not_affect_vault_b(self):
        cypher = self._get_delete_call(vault_name="vault_a")
        self.assertIn("vault: $vault_name", cypher)
        self.assertNotIn("()-[r:", cypher)

    def test_full_sync_empty_vault_name_legacy(self):
        cypher = self._get_delete_call(vault_name="")
        self.assertIn("()-[r:", cypher)
        self.assertNotIn("$vault_name", cypher)


class TestSyncGraphVaultProperty(unittest.TestCase):
    def setUp(self):
        self.driver = MagicMock()
        self.session = MagicMock()
        self.session.__enter__.return_value = self.session
        self.tx = MagicMock()
        self.tx.__enter__.return_value = self.tx
        self.session.begin_transaction.return_value = self.tx
        self.driver.session.return_value = self.session

        self.note_records: list[NoteRecord] = [
            {
                "name": "note1.md",
                "path": "note1.md",
                "source": "/vault/note1.md",
                "content": "Content 1",
                "tags": ["tag-a"],
                "wikilinks": [],
                "chunks": [{"header": "", "content": "Content 1", "order": 0}],
            }
        ]

    def test_sync_graph_includes_vault_property(self):
        sync_graph(self.driver, self.note_records, vault_name="general")

        call = self.tx.run.call_args_list[0]
        cypher = call[0][0]
        kwargs = call[1]

        self.assertIn("vault: file.vault", cypher)
        self.assertEqual(kwargs["files"][0]["vault"], "general")

    def test_sync_graph_empty_vault_name(self):
        sync_graph(self.driver, self.note_records, vault_name="")

        call = self.tx.run.call_args_list[0]
        kwargs = call[1]

        self.assertEqual(kwargs["files"][0]["vault"], "")


class TestIndexNamedVault(unittest.TestCase):
    @patch("clawdiney.indexer.Config.get_vault_path")
    @patch("clawdiney.indexer._index_vault_inner")
    def test_index_named_vault_calls_inner_with_name(
        self, mock_inner, mock_get_path
    ):
        mock_get_path.return_value = Path("/fake/vault")
        mock_inner.return_value = {"vault_name": "general"}

        result = index_named_vault("general")

        mock_get_path.assert_called_once_with("general")
        mock_inner.assert_called_once()
        kwargs = mock_inner.call_args.kwargs
        self.assertEqual(kwargs["vault_name"], "general")
        self.assertEqual(result["vault_name"], "general")


class TestIndexAllVaults(unittest.TestCase):
    @patch("clawdiney.indexer.Config.get_all_vaults")
    @patch("clawdiney.indexer.index_named_vault")
    def test_index_all_vaults_iterates_all(self, mock_index_named, mock_get_all):
        mock_get_all.return_value = {
            "general": Path("/vaults/general"),
            "projects": Path("/vaults/projects"),
        }
        mock_index_named.side_effect = lambda name, **kw: {"vault_name": name}

        results = index_all_vaults()

        self.assertIn("general", results)
        self.assertIn("projects", results)
        self.assertEqual(results["general"]["vault_name"], "general")
        self.assertEqual(results["projects"]["vault_name"], "projects")
        self.assertEqual(mock_index_named.call_count, 2)


class TestIndexVaultLegacyCompat(unittest.TestCase):
    @patch("clawdiney.indexer._index_vault_inner")
    def test_index_vault_calls_inner_with_empty_vault_name(self, mock_inner):
        mock_inner.return_value = {"vault_name": None}

        result = index_vault()

        mock_inner.assert_called_once()
        kwargs = mock_inner.call_args.kwargs
        self.assertEqual(kwargs["vault_name"], "")
        self.assertIsNone(result["vault_name"])


if __name__ == "__main__":
    unittest.main()
