"""Tests for sync_vault CLI script."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import clawdiney.scripts.sync_vault as sync_mod


class TestSyncVault:
    def test_main_accepts_vault_flag(self):
        with (
            patch.object(sync_mod, "setup_logging"),
            patch.object(sync_mod, "run_sync") as mock_run,
        ):
            with patch("sys.argv", ["sync_vault.py", "--vault", "projects"]):
                sync_mod.main()
            mock_run.assert_called_once_with(full=False, vault_name="projects")

    def test_main_accepts_vault_full_flag(self):
        with (
            patch.object(sync_mod, "setup_logging"),
            patch.object(sync_mod, "run_sync") as mock_run,
        ):
            with patch("sys.argv", ["sync_vault.py", "--vault", "projects", "--full"]):
                sync_mod.main()
            mock_run.assert_called_once_with(full=True, vault_name="projects")

    def test_main_no_flags_calls_sync_all(self):
        with (
            patch.object(sync_mod, "setup_logging"),
            patch.object(sync_mod, "run_sync") as mock_run,
        ):
            with patch("sys.argv", ["sync_vault.py"]):
                sync_mod.main()
            mock_run.assert_called_once_with(full=False, vault_name="")

    def test_main_full_flag(self):
        with (
            patch.object(sync_mod, "setup_logging"),
            patch.object(sync_mod, "run_sync") as mock_run,
        ):
            with patch("sys.argv", ["sync_vault.py", "--full"]):
                sync_mod.main()
            mock_run.assert_called_once_with(full=True, vault_name="")

    def test_main_status_flag(self):
        with (
            patch.object(sync_mod, "setup_logging"),
            patch.object(sync_mod, "show_status") as mock_status,
        ):
            with patch("sys.argv", ["sync_vault.py", "--status"]):
                sync_mod.main()
            mock_status.assert_called_once_with(vault_name="")

    def test_main_status_with_vault(self):
        with (
            patch.object(sync_mod, "setup_logging"),
            patch.object(sync_mod, "show_status") as mock_status,
        ):
            with patch("sys.argv", ["sync_vault.py", "--status", "--vault", "projects"]):
                sync_mod.main()
            mock_status.assert_called_once_with(vault_name="projects")

    @patch("clawdiney.scripts.sync_vault.Config")
    def test_show_status_single_vault(self, mock_config):
        mock_config.get_vault_path.return_value = "/fake/vaults/projects"

        with (
            patch("clawdiney.incremental_indexer.IncrementalIndexer"),
            patch.object(Path, "exists", return_value=False),
        ):
            sync_mod.show_status(vault_name="projects")

        mock_config.get_vault_path.assert_called_once_with("projects")

    @patch("clawdiney.scripts.sync_vault.Config")
    def test_show_status_all_vaults(self, mock_config):
        mock_config.get_all_vaults.return_value = {
            "personal": Path("/fake/personal"),
            "projects": Path("/fake/projects"),
        }

        with (
            patch("clawdiney.incremental_indexer.IncrementalIndexer"),
            patch.object(Path, "exists", return_value=False),
        ):
            sync_mod.show_status(vault_name="")

        mock_config.get_all_vaults.assert_called_once()

    @patch("clawdiney.scripts.sync_vault.Config")
    def test_run_sync_specific_vault(self, mock_config):
        mock_config.get_vault_path.return_value = "/fake/vaults/projects"

        with (
            patch("clawdiney.indexer.create_chroma_client"),
            patch("clawdiney.indexer.create_collection"),
            patch("clawdiney.indexer.create_neo4j_driver") as mock_driver,
            patch("clawdiney.incremental_indexer.incremental_sync") as mock_sync,
        ):
            mock_driver.return_value.__enter__.return_value = MagicMock()
            mock_sync.return_value = {
                "sync_type": "incremental",
                "files_synced": 5,
                "files_deleted": 0,
                "indexed_chunks": 42,
            }
            sync_mod.run_sync(full=False, vault_name="projects")

        mock_sync.assert_called_once()
        _, kwargs = mock_sync.call_args
        assert kwargs["vault_name"] == "projects"

    @patch("clawdiney.scripts.sync_vault.Config")
    def test_run_sync_all_vaults(self, mock_config):
        with (
            patch("clawdiney.indexer.create_chroma_client"),
            patch("clawdiney.indexer.create_collection"),
            patch("clawdiney.indexer.create_neo4j_driver") as mock_driver,
            patch("clawdiney.incremental_indexer.incremental_sync_all_vaults") as mock_sync_all,
        ):
            mock_driver.return_value.__enter__.return_value = MagicMock()
            mock_sync_all.return_value = {}
            sync_mod.run_sync(full=False, vault_name="")

        mock_sync_all.assert_called_once()

    @patch("clawdiney.scripts.sync_vault.Config")
    def test_run_sync_full_vault(self, mock_config):
        mock_config.get_vault_path.return_value = "/fake/vaults/projects"

        with (
            patch("clawdiney.indexer.create_chroma_client"),
            patch("clawdiney.indexer.create_collection"),
            patch("clawdiney.indexer.create_neo4j_driver") as mock_driver,
            patch("clawdiney.incremental_indexer.full_sync") as mock_full,
        ):
            mock_driver.return_value.__enter__.return_value = MagicMock()
            mock_full.return_value = {
                "sync_type": "full",
                "files_synced": 100,
                "files_deleted": 0,
                "indexed_chunks": 500,
            }
            sync_mod.run_sync(full=True, vault_name="projects")

        mock_full.assert_called_once()
        _, kwargs = mock_full.call_args
        assert kwargs["vault_name"] == "projects"
