from pathlib import Path
from unittest.mock import MagicMock, patch

import clawdiney.vault_writer as vw_mod
import pytest

from clawdiney.vault_writer import VaultWriter, get_writer


@pytest.fixture(autouse=True)
def mock_chroma_and_neo4j():
    with (
        patch.object(VaultWriter, "_get_collection", return_value=MagicMock()),
        patch.object(VaultWriter, "_get_neo4j_driver", return_value=MagicMock()),
    ):
        yield


@pytest.fixture
def vault_root(tmp_path: Path) -> Path:
    vault = tmp_path / "vault"
    vault.mkdir()
    return vault


@pytest.fixture
def vault_root_general(tmp_path: Path) -> Path:
    vault = tmp_path / "general"
    vault.mkdir()
    return vault


@pytest.fixture
def vault_root_projects(tmp_path: Path) -> Path:
    vault = tmp_path / "projects"
    vault.mkdir()
    return vault


def test_write_note_with_vault_name(vault_root: Path) -> None:
    writer = VaultWriter(vault_root, vault_name="my_vault")
    assert writer.vault_name == "my_vault"
    assert writer.vault_root == vault_root

    result = writer.write_note("test_note.md", "# Test Content")
    assert result["success"] is True
    assert (vault_root / "test_note.md").exists()
    assert (vault_root / "test_note.md").read_text(encoding="utf-8") == "# Test Content"


def test_write_note_legacy_no_vault_name(vault_root: Path) -> None:
    writer = VaultWriter(vault_root)
    assert writer.vault_name is None

    result = writer.write_note("test_note.md", "# Legacy Content")
    assert result["success"] is True
    assert (vault_root / "test_note.md").read_text(encoding="utf-8") == "# Legacy Content"


def test_write_note_reindex_called_with_vault_name(vault_root: Path) -> None:
    writer = VaultWriter(vault_root, vault_name="custom_vault")
    writer._get_collection = MagicMock(return_value=MagicMock())
    writer._get_neo4j_driver = MagicMock(return_value=MagicMock())
    writer.indexer.sync_file = MagicMock(return_value=True)
    writer.indexer._get_all_vault_files = MagicMock(return_value={vault_root / "test.md": ""})

    result = writer.write_note("test.md", "# Content")
    assert result["success"] is True

    writer.indexer.sync_file.assert_called_once()
    _, kwargs = writer.indexer.sync_file.call_args
    assert kwargs.get("vault_name") == "custom_vault"


def test_write_note_reindex_called_without_vault_name(vault_root: Path) -> None:
    writer = VaultWriter(vault_root)
    writer._get_collection = MagicMock(return_value=MagicMock())
    writer._get_neo4j_driver = MagicMock(return_value=MagicMock())
    writer.indexer.sync_file = MagicMock(return_value=True)
    writer.indexer._get_all_vault_files = MagicMock(return_value={vault_root / "test.md": ""})

    result = writer.write_note("test.md", "# Content")
    assert result["success"] is True

    writer.indexer.sync_file.assert_called_once()
    _, kwargs = writer.indexer.sync_file.call_args
    assert kwargs.get("vault_name") == ""


def test_get_writer_with_vault_name(vault_root_general: Path, vault_root_projects: Path) -> None:
    with (
        patch("clawdiney.config.Config._is_multi_vault", return_value=True),
        patch("clawdiney.config.Config.get_vault_path") as mock_get_path,
    ):
        def _get_path(name: str) -> Path:
            mapping = {"general": vault_root_general, "projects": vault_root_projects}
            return mapping[name]

        mock_get_path.side_effect = _get_path

        vw_mod._writer_lock = None
        vw_mod._writer_instances.clear()

        w1 = get_writer(vault_name="general")
        w2 = get_writer(vault_name="projects")
        w3 = get_writer(vault_name="general")

        assert w1 is w3, "Same vault_name should return same instance"
        assert w1 is not w2, "Different vault_names should return different instances"
        assert w1.vault_root == vault_root_general
        assert w2.vault_root == vault_root_projects


def test_get_writer_legacy_no_vault_name(vault_root: Path, monkeypatch) -> None:
    monkeypatch.delenv("VAULTS", raising=False)
    with patch("clawdiney.config.Config.VAULT_PATH", str(vault_root)):
        vw_mod._writer_lock = None
        vw_mod._writer_instances.clear()

        writer = get_writer()
        assert writer.vault_name is None
        assert writer.vault_root.resolve() == vault_root.resolve()


def test_get_writer_default_vault_in_multi_vault_mode(vault_root_general: Path) -> None:
    with (
        patch("clawdiney.config.Config._is_multi_vault", return_value=True),
        patch("clawdiney.config.Config.get_default_vault", return_value="general"),
        patch("clawdiney.config.Config.get_vault_path", return_value=vault_root_general),
    ):
        vw_mod._writer_lock = None
        vw_mod._writer_instances.clear()

        writer = get_writer()
        assert writer.vault_name == "general"
        assert writer.vault_root == vault_root_general


def test_append_to_daily_with_vault_name(vault_root: Path) -> None:
    writer = VaultWriter(vault_root, vault_name="my_vault")
    writer._get_collection = MagicMock(return_value=MagicMock())
    writer._get_neo4j_driver = MagicMock(return_value=MagicMock())
    writer.indexer.sync_file = MagicMock(return_value=True)
    writer.indexer._get_all_vault_files = MagicMock(return_value={})
    writer.indexer._compute_file_hash = MagicMock(return_value="abc")

    from datetime import date

    result = writer.append_to_daily("Daily content", date="2025-01-15")
    assert result["success"] is True

    path = vault_root / "50_Daily" / "2025-01-15.md"
    assert path.exists()
    assert "Daily content" in path.read_text(encoding="utf-8")


def test_delete_note_with_vault_name(vault_root: Path) -> None:
    writer = VaultWriter(vault_root, vault_name="my_vault")

    note_path = vault_root / "delete_me.md"
    note_path.write_text("# To delete")

    writer._get_collection = MagicMock()
    mock_collection = MagicMock()
    mock_collection.get.return_value = {"ids": []}
    writer._get_collection = MagicMock(return_value=mock_collection)

    result = writer.delete_note("delete_me.md")
    assert result["success"] is True
    assert not note_path.exists()
