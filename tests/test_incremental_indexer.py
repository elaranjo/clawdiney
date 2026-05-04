import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from clawdiney.incremental_indexer import (
    incremental_sync,
    incremental_sync_all_vaults,
)


class TestIncrementalSyncVaultName(unittest.TestCase):
    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    @patch("clawdiney.indexer.create_chroma_client")
    @patch("clawdiney.indexer.create_collection")
    @patch("clawdiney.indexer.create_neo4j_driver")
    @patch("clawdiney.incremental_indexer.Config.get_vault_path")
    def test_incremental_sync_with_vault_name_uses_correct_path(
        self, mock_get_path, mock_create_driver, mock_create_coll, mock_create_client
    ):
        vault_root = self.tmpdir / "projects"
        vault_root.mkdir()
        mock_get_path.return_value = vault_root.resolve()
        mock_collection = MagicMock()
        mock_create_coll.return_value = mock_collection
        mock_driver = MagicMock()
        mock_create_driver.return_value = mock_driver
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        result = incremental_sync(vault_name="projects")

        mock_get_path.assert_called_once_with("projects")
        self.assertIn("vault_name", result)
        self.assertEqual(result["vault_name"], "projects")

    @patch("clawdiney.indexer.create_chroma_client")
    @patch("clawdiney.indexer.create_collection")
    @patch("clawdiney.indexer.create_neo4j_driver")
    def test_incremental_sync_without_vault_name_uses_vault_path(
        self, mock_create_driver, mock_create_coll, mock_create_client
    ):
        vault_root = self.tmpdir / "legacy"
        vault_root.mkdir()
        mock_collection = MagicMock()
        mock_create_coll.return_value = mock_collection
        mock_driver = MagicMock()
        mock_create_driver.return_value = mock_driver
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        with patch(
            "clawdiney.incremental_indexer.Config.VAULT_PATH", str(vault_root)
        ):
            result = incremental_sync()

        self.assertNotIn("vault_name", result)

    @patch("clawdiney.indexer.create_chroma_client")
    @patch("clawdiney.indexer.create_collection")
    @patch("clawdiney.indexer.create_neo4j_driver")
    @patch("clawdiney.incremental_indexer.Config.get_all_vaults")
    def test_incremental_sync_all_vaults_iterates_all(
        self, mock_get_all, mock_create_driver, mock_create_coll, mock_create_client
    ):
        general_root = self.tmpdir / "general"
        projects_root = self.tmpdir / "projects"
        general_root.mkdir()
        projects_root.mkdir()
        mock_get_all.return_value = {
            "general": general_root,
            "projects": projects_root,
        }
        mock_collection = MagicMock()
        mock_create_coll.return_value = mock_collection
        mock_driver = MagicMock()
        mock_create_driver.return_value = mock_driver
        mock_session = MagicMock()
        mock_driver.session.return_value.__enter__.return_value = mock_session

        with patch(
            "clawdiney.incremental_indexer.Config.get_vault_path",
            side_effect=lambda name: self.tmpdir / name,
        ):
            results = incremental_sync_all_vaults()

        self.assertIn("general", results)
        self.assertIn("projects", results)
        self.assertEqual(results["general"]["vault_name"], "general")
        self.assertEqual(results["projects"]["vault_name"], "projects")


if __name__ == "__main__":
    unittest.main()
