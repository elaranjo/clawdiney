"""Incremental indexer vault-path selection tests (real storage, fake embedder)."""

import pytest

from clawdiney.incremental_indexer import incremental_sync, incremental_sync_all_vaults
from clawdiney.storage import BrainStorage

DIM = 4


class FakeProvider:
    def embed(self, text):
        return [float(len(text) % 97), 1.0, 2.0, 3.0]

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]


@pytest.fixture()
def storage(tmp_path):
    store = BrainStorage(db_path=tmp_path / "brain.db", dimension=DIM)
    yield store
    store.close()


def _make_vault(base, name):
    root = base / name
    root.mkdir(parents=True)
    (root / f"{name}_note.md").write_text(f"# {name}\n\nbody", encoding="utf-8")
    return root


def test_sync_with_vault_name_uses_configured_path(tmp_path, storage, monkeypatch):
    vault_a = _make_vault(tmp_path, "a")
    monkeypatch.setattr(
        "clawdiney.config.Config.get_vault_path", classmethod(lambda cls, v: vault_a)
    )
    result = incremental_sync(storage=storage, vault_name="a", provider=FakeProvider())
    assert result["vault_name"] == "a"
    assert "a_note.md" in storage.get_document_hashes("a")


def test_sync_without_vault_name_uses_vault_path(tmp_path, storage, monkeypatch):
    vault = _make_vault(tmp_path, "solo")
    monkeypatch.setattr("clawdiney.config.Config.VAULT_PATH", str(vault))
    result = incremental_sync(storage=storage, provider=FakeProvider())
    assert result["files_synced"] == 1
    assert "solo_note.md" in storage.get_document_hashes("default")


def test_sync_all_vaults_iterates_all(tmp_path, storage, monkeypatch):
    vaults = {"a": _make_vault(tmp_path, "a"), "b": _make_vault(tmp_path, "b")}
    monkeypatch.setattr(
        "clawdiney.config.Config.get_all_vaults", classmethod(lambda cls: vaults)
    )
    monkeypatch.setattr(
        "clawdiney.config.Config.get_vault_path",
        classmethod(lambda cls, v: vaults[v]),
    )
    results = incremental_sync_all_vaults(storage=storage, provider=FakeProvider())
    assert set(results) == {"a", "b"}
    assert "a_note.md" in storage.get_document_hashes("a")
    assert "b_note.md" in storage.get_document_hashes("b")
