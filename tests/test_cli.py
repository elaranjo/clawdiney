import os
import sys
from pathlib import Path

import pytest

from clawdiney.cli import main


def test_create_with_explicit_path(monkeypatch, tmp_path):
    vault_dir = tmp_path / "my_vault"
    monkeypatch.setattr(sys, "argv", ["clawdiney", "vault", "create", "my_vault", "--path", str(vault_dir)])
    main()
    assert vault_dir.exists()
    assert (vault_dir / "clawdiney.toml").exists()
    content = (vault_dir / "clawdiney.toml").read_text()
    assert 'id = "my_vault"' in content
    assert 'name = "my_vault"' in content


def test_create_without_path_and_vaults_dir(monkeypatch):
    monkeypatch.delenv("VAULTS_DIR", raising=False)
    monkeypatch.setattr(sys, "argv", ["clawdiney", "vault", "create", "my_vault"])
    with pytest.raises(SystemExit):
        main()


def test_create_with_vaults_dir(monkeypatch, tmp_path):
    vaults_dir = tmp_path / "vaults"
    monkeypatch.setenv("VAULTS_DIR", str(vaults_dir))
    monkeypatch.setattr(sys, "argv", ["clawdiney", "vault", "create", "my_vault"])
    main()
    assert (vaults_dir / "my_vault").exists()
    assert (vaults_dir / "my_vault" / "clawdiney.toml").exists()


def test_create_existing_directory(monkeypatch, tmp_path):
    vault_dir = tmp_path / "existing"
    vault_dir.mkdir()
    monkeypatch.setattr(sys, "argv", ["clawdiney", "vault", "create", "existing", "--path", str(vault_dir)])
    with pytest.raises(SystemExit):
        main()


def test_create_invalid_id(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["clawdiney", "vault", "create", "invalid@id"])
    with pytest.raises(SystemExit):
        main()


def test_list_with_vaults(monkeypatch, tmp_path, capsys):
    vault_dir = tmp_path / "test_vault"
    vault_dir.mkdir(parents=True)
    toml_content = 'id = "test_vault"\nname = "Test Vault"\n'
    (vault_dir / "clawdiney.toml").write_text(toml_content)
    monkeypatch.setattr("clawdiney.cli.Config.get_all_vaults", lambda: {"test_vault": vault_dir})
    monkeypatch.setattr(sys, "argv", ["clawdiney", "vault", "list"])
    main()
    captured = capsys.readouterr()
    assert "Vaults:" in captured.out
    assert "test_vault" in captured.out


def test_list_no_vaults(monkeypatch, capsys):
    monkeypatch.setattr("clawdiney.cli.Config.get_all_vaults", lambda: {})
    monkeypatch.setattr(sys, "argv", ["clawdiney", "vault", "list"])
    main()
    captured = capsys.readouterr()
    assert "No vaults configured" in captured.out
