"""Tests for clawdiney.config.Config multi-vault support."""

import os
from pathlib import Path

import pytest


class TestMultiVault:
    def setup_method(self):
        import clawdiney.config as cfg

        cfg.load_dotenv()
        self._cfg = cfg

    def test_single_vault_default(self, monkeypatch):
        monkeypatch.delenv("VAULTS_DIR", raising=False)
        monkeypatch.delenv("VAULTS", raising=False)
        self._cfg.Config.VAULT_PATH = Path("/tmp/test-vault")

        assert self._cfg.Config._is_multi_vault() is False
        assert self._cfg.Config.get_default_vault() == "default"

    def test_multi_vault_three_vaults(self, monkeypatch):
        monkeypatch.delenv("VAULTS_DIR", raising=False)
        monkeypatch.setenv("VAULTS", "general, projects, archive")
        monkeypatch.setenv("VAULT_GENERAL_PATH", "/tmp/vault-general")
        monkeypatch.setenv("VAULT_PROJECTS_PATH", "/tmp/vault-projects")
        monkeypatch.setenv("VAULT_ARCHIVE_PATH", "/tmp/vault-archive")

        vaults = self._cfg.Config.get_all_vaults()
        assert set(vaults.keys()) == {"general", "projects", "archive"}
        assert vaults["general"] == Path("/tmp/vault-general")
        assert vaults["projects"] == Path("/tmp/vault-projects")
        assert vaults["archive"] == Path("/tmp/vault-archive")

    def test_multi_vault_get_vault_path(self, monkeypatch):
        monkeypatch.delenv("VAULTS_DIR", raising=False)
        monkeypatch.setenv("VAULTS", "general, projects")
        monkeypatch.setenv("VAULT_GENERAL_PATH", "/tmp/vault-general")
        monkeypatch.setenv("VAULT_PROJECTS_PATH", "/tmp/vault-projects")

        assert self._cfg.Config.get_vault_path("general") == Path("/tmp/vault-general")
        assert self._cfg.Config.get_vault_path("projects") == Path("/tmp/vault-projects")

    def test_invalid_vault_id_raises_keyerror(self, monkeypatch):
        monkeypatch.delenv("VAULTS_DIR", raising=False)
        monkeypatch.setenv("VAULTS", "general")
        monkeypatch.setenv("VAULT_GENERAL_PATH", "/tmp/vault-general")

        with pytest.raises(KeyError, match="not configured"):
            self._cfg.Config.get_vault_path("nonexistent")

    def test_tilde_expansion(self, monkeypatch):
        monkeypatch.delenv("VAULTS_DIR", raising=False)
        monkeypatch.setenv("VAULTS", "general")
        monkeypatch.setenv("VAULT_GENERAL_PATH", "~/my-vault")

        vaults = self._cfg.Config.get_all_vaults()
        assert str(vaults["general"]).startswith("/")
        assert "~" not in str(vaults["general"])

    def test_vaults_with_spaces(self, monkeypatch):
        monkeypatch.delenv("VAULTS_DIR", raising=False)
        monkeypatch.setenv("VAULTS", " general , projects ")
        monkeypatch.setenv("VAULT_GENERAL_PATH", "/tmp/vault-general")
        monkeypatch.setenv("VAULT_PROJECTS_PATH", "/tmp/vault-projects")

        vaults = self._cfg.Config.get_all_vaults()
        assert set(vaults.keys()) == {"general", "projects"}

    def test_default_vault_from_env(self, monkeypatch):
        monkeypatch.delenv("VAULTS_DIR", raising=False)
        monkeypatch.setenv("VAULTS", "general, projects, archive")
        monkeypatch.setenv("MCP_DEFAULT_VAULT", "projects")
        monkeypatch.setenv("VAULT_GENERAL_PATH", "/tmp/vault-general")
        monkeypatch.setenv("VAULT_PROJECTS_PATH", "/tmp/vault-projects")
        monkeypatch.setenv("VAULT_ARCHIVE_PATH", "/tmp/vault-archive")

        assert self._cfg.Config.get_default_vault() == "projects"

    def test_default_vault_first_in_list(self, monkeypatch):
        monkeypatch.delenv("VAULTS_DIR", raising=False)
        monkeypatch.delenv("MCP_DEFAULT_VAULT", raising=False)
        monkeypatch.setenv("VAULTS", "alpha, beta")
        monkeypatch.setenv("VAULT_ALPHA_PATH", "/tmp/alpha")
        monkeypatch.setenv("VAULT_BETA_PATH", "/tmp/beta")

        assert self._cfg.Config.get_default_vault() == "alpha"

    def test_legacy_vault_path_still_works(self):
        assert hasattr(self._cfg.Config, "VAULT_PATH")
        assert isinstance(self._cfg.Config.VAULT_PATH, Path)

    def test_multi_vault_single_vault_id(self, monkeypatch):
        monkeypatch.delenv("VAULTS_DIR", raising=False)
        monkeypatch.setenv("VAULTS", "docs")
        monkeypatch.setenv("VAULT_DOCS_PATH", "/tmp/mydocs")

        vaults = self._cfg.Config.get_all_vaults()
        assert vaults == {"docs": Path("/tmp/mydocs")}


def _write_toml(path: Path, data: dict) -> None:
    lines = []
    for k, v in data.items():
        if isinstance(v, list):
            items = ", ".join(f'"{x}"' for x in v)
            lines.append(f'{k} = [{items}]')
        elif isinstance(v, str):
            lines.append(f'{k} = "{v}"')
        elif isinstance(v, bool):
            lines.append(f'{k} = {"true" if v else "false"}')
        else:
            lines.append(f'{k} = {v}')
    path.write_text("\n".join(lines) + "\n")


def _create_vault_dir(
    base: Path, name: str, vault_id: str, linked: list[str] | None = None
) -> Path:
    d = base / name
    d.mkdir(parents=True, exist_ok=True)
    data = {"id": vault_id, "name": name}
    if linked:
        data["linked_vaults"] = linked
    _write_toml(d / "clawdiney.toml", data)
    return d


class TestVaultsDir:
    def setup_method(self):
        import clawdiney.config as cfg

        cfg.load_dotenv()
        self._cfg = cfg

    def test_discover_three_vaults(self, monkeypatch, tmp_path):
        _create_vault_dir(tmp_path, "docs", "docs")
        _create_vault_dir(tmp_path, "projects", "proj")
        _create_vault_dir(tmp_path, "archive", "arch")
        monkeypatch.setenv("VAULTS_DIR", str(tmp_path))
        monkeypatch.delenv("VAULTS", raising=False)

        vaults = self._cfg.Config.get_all_vaults()
        assert set(vaults.keys()) == {"docs", "proj", "arch"}

    def test_dir_without_toml_is_ignored(self, monkeypatch, tmp_path):
        _create_vault_dir(tmp_path, "alpha", "alpha")
        (tmp_path / "no-toml").mkdir(exist_ok=True)
        monkeypatch.setenv("VAULTS_DIR", str(tmp_path))
        monkeypatch.delenv("VAULTS", raising=False)

        vaults = self._cfg.Config.get_all_vaults()
        assert set(vaults.keys()) == {"alpha"}

    def test_duplicate_id_skipped(self, monkeypatch, tmp_path, caplog):
        _create_vault_dir(tmp_path, "first", "dup")
        _create_vault_dir(tmp_path, "second", "dup")
        monkeypatch.setenv("VAULTS_DIR", str(tmp_path))
        monkeypatch.delenv("VAULTS", raising=False)

        vaults = self._cfg.Config.get_all_vaults()
        assert list(vaults.keys()) == ["dup"]
        assert vaults["dup"].name == "first"
        assert any("Duplicate vault id" in msg for msg in caplog.messages)

    def test_nonexistent_dir_returns_empty(self, monkeypatch, caplog):
        monkeypatch.setenv("VAULTS_DIR", "/tmp/nonexistent-vaults-dir")
        monkeypatch.delenv("VAULTS", raising=False)

        vaults = self._cfg.Config.get_all_vaults()
        assert vaults == {}
        assert any("not a directory" in msg for msg in caplog.messages)

    def test_valid_linked_vaults(self, monkeypatch, tmp_path):
        _create_vault_dir(tmp_path, "main", "main", linked=["sub"])
        _create_vault_dir(tmp_path, "sub", "sub")
        monkeypatch.setenv("VAULTS_DIR", str(tmp_path))
        monkeypatch.delenv("VAULTS", raising=False)

        vaults = self._cfg.Config.get_all_vaults()
        assert set(vaults.keys()) == {"main", "sub"}

    def test_cycle_in_linked_vaults(self, monkeypatch, tmp_path):
        _create_vault_dir(tmp_path, "a", "a", linked=["b"])
        _create_vault_dir(tmp_path, "b", "b", linked=["c"])
        _create_vault_dir(tmp_path, "c", "c", linked=["a"])
        monkeypatch.setenv("VAULTS_DIR", str(tmp_path))
        monkeypatch.delenv("VAULTS", raising=False)

        vaults = self._cfg.Config.get_all_vaults()
        assert vaults == {}

    def test_vaults_dir_with_legacy_vault_path(self, monkeypatch, tmp_path):
        _create_vault_dir(tmp_path, "mydocs", "mydocs")
        monkeypatch.setenv("VAULTS_DIR", str(tmp_path))
        monkeypatch.setenv("VAULT_PATH", "/tmp/legacy-vault")
        monkeypatch.delenv("VAULTS", raising=False)

        vaults = self._cfg.Config.get_all_vaults()
        assert list(vaults.keys()) == ["mydocs"]
