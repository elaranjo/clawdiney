"""Tests for the vault_config module."""

import tempfile
from pathlib import Path

import pytest

from clawdiney.vault_config import VaultConfig, load_vault_config, validate_linked_vaults


def _write_toml(path: Path, content: str) -> Path:
    (path / "clawdiney.toml").write_text(content)
    return path


class TestLoadVaultConfig:
    def test_valid_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_root = _write_toml(Path(tmpdir), """
id = "vault_general"
name = "General Vault"
description = "A general vault"
linked_vaults = ["vault_projects"]
include_patterns = ["**/*.md"]
exclude_patterns = ["drafts/**"]
""")
            config = load_vault_config(vault_root)

            assert config.id == "vault_general"
            assert config.name == "General Vault"
            assert config.description == "A general vault"
            assert config.linked_vaults == ["vault_projects"]
            assert config.include_patterns == ["**/*.md"]
            assert config.exclude_patterns == ["drafts/**"]

    def test_minimal_config(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_root = _write_toml(Path(tmpdir), """
id = "vault_minimal"
name = "Minimal"
""")
            config = load_vault_config(vault_root)

            assert config.id == "vault_minimal"
            assert config.name == "Minimal"
            assert config.description == ""
            assert config.linked_vaults == []
            assert config.include_patterns == []
            assert config.exclude_patterns == []

    def test_missing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(ValueError, match="clawdiney.toml not found"):
                load_vault_config(Path(tmpdir))

    def test_missing_id(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_root = _write_toml(Path(tmpdir), 'name = "No ID"')
            with pytest.raises(ValueError, match="Missing required field 'id'"):
                load_vault_config(vault_root)

    def test_missing_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_root = _write_toml(Path(tmpdir), 'id = "no_name"')
            with pytest.raises(ValueError, match="Missing required field 'name'"):
                load_vault_config(vault_root)

    def test_empty_linked_vaults(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            vault_root = _write_toml(Path(tmpdir), """
id = "vault_standalone"
name = "Standalone Vault"
linked_vaults = []
""")
            config = load_vault_config(vault_root)
            assert config.linked_vaults == []


class TestValidateLinkedVaults:
    def test_no_linked_vaults(self):
        configs = {
            "a": VaultConfig(id="a", name="A"),
            "b": VaultConfig(id="b", name="B"),
        }
        validate_linked_vaults(configs)

    def test_valid_linked_vaults(self):
        configs = {
            "a": VaultConfig(id="a", name="A", linked_vaults=["b"]),
            "b": VaultConfig(id="b", name="B", linked_vaults=["c"]),
            "c": VaultConfig(id="c", name="C"),
        }
        validate_linked_vaults(configs)

    def test_nonexistent_linked_vault(self):
        configs = {
            "a": VaultConfig(id="a", name="A", linked_vaults=["nonexistent"]),
        }
        with pytest.raises(ValueError, match="does not exist"):
            validate_linked_vaults(configs)

    def test_direct_cycle(self):
        configs = {
            "a": VaultConfig(id="a", name="A", linked_vaults=["b"]),
            "b": VaultConfig(id="b", name="B", linked_vaults=["a"]),
        }
        with pytest.raises(ValueError, match="Cycle detected"):
            validate_linked_vaults(configs)

    def test_indirect_cycle(self):
        configs = {
            "a": VaultConfig(id="a", name="A", linked_vaults=["b"]),
            "b": VaultConfig(id="b", name="B", linked_vaults=["c"]),
            "c": VaultConfig(id="c", name="C", linked_vaults=["a"]),
        }
        with pytest.raises(ValueError, match="Cycle detected"):
            validate_linked_vaults(configs)

    def test_self_cycle(self):
        configs = {
            "a": VaultConfig(id="a", name="A", linked_vaults=["a"]),
        }
        with pytest.raises(ValueError, match="Cycle detected"):
            validate_linked_vaults(configs)

    def test_cycle_with_unrelated_vaults(self):
        configs = {
            "a": VaultConfig(id="a", name="A", linked_vaults=["b"]),
            "b": VaultConfig(id="b", name="B", linked_vaults=["c"]),
            "c": VaultConfig(id="c", name="C", linked_vaults=["b"]),
            "d": VaultConfig(id="d", name="D"),
            "e": VaultConfig(id="e", name="E", linked_vaults=["d"]),
        }
        with pytest.raises(ValueError, match="Cycle detected"):
            validate_linked_vaults(configs)
