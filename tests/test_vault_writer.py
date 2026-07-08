"""VaultWriter tests against real tempfile storage (fake embedder)."""

import pytest

import clawdiney.vault_writer as vw_module
from clawdiney.storage import BrainStorage
from clawdiney.vault_writer import VaultWriter, get_writer

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


@pytest.fixture()
def writer(tmp_path, storage):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    w = VaultWriter(vault_root, storage=storage, vault_name="default")
    w.indexer._provider = FakeProvider()
    return w


class TestWriteNote:
    def test_create_writes_and_indexes(self, writer, storage):
        result = writer.write_note("notes/new.md", "# New\n\ncontent body")
        assert result["success"]
        assert result["chunks_indexed"] >= 1
        assert "notes/new.md" in storage.get_document_hashes("default")

    def test_create_fails_if_exists(self, writer):
        writer.write_note("a.md", "# A")
        result = writer.write_note("a.md", "# A again")
        assert not result["success"]
        assert "already exists" in result["message"]

    def test_overwrite_replaces(self, writer):
        writer.write_note("a.md", "# v1")
        result = writer.write_note("a.md", "# v2", mode="overwrite")
        assert result["success"]
        assert (writer.vault_root / "a.md").read_text() == "# v2"

    def test_append_adds_content(self, writer):
        writer.write_note("a.md", "# A")
        result = writer.write_note("a.md", "more", mode="append")
        assert result["success"]
        assert "more" in (writer.vault_root / "a.md").read_text()

    def test_rejects_absolute_path(self, writer):
        result = writer.write_note("/etc/evil.md", "x")
        assert not result["success"]

    def test_rejects_traversal(self, writer):
        result = writer.write_note("../outside.md", "x")
        assert not result["success"]


class TestDeleteNote:
    def test_delete_removes_file_and_index(self, writer, storage):
        writer.write_note("a.md", "# A body text")
        result = writer.delete_note("a.md")
        assert result["success"]
        assert not (writer.vault_root / "a.md").exists()
        assert "a.md" not in storage.get_document_hashes("default")

    def test_delete_missing_fails(self, writer):
        result = writer.delete_note("nope.md")
        assert not result["success"]


class TestAppendToDaily:
    def test_creates_daily_note(self, writer):
        result = writer.append_to_daily("## Log entry", date="2026-07-08")
        assert result["success"]
        assert (writer.vault_root / "50_Daily" / "2026-07-08.md").exists()


class TestGetWriter:
    def test_singleton_per_key(self, tmp_path, storage, monkeypatch):
        monkeypatch.delenv("VAULTS_DIR", raising=False)
        monkeypatch.delenv("VAULTS", raising=False)
        vw_module._writer_instances.clear()
        vault_root = tmp_path / "v"
        vault_root.mkdir()
        w1 = get_writer(vault_root=vault_root, storage=storage)
        w2 = get_writer(vault_root=vault_root, storage=storage)
        assert w1 is w2
        vw_module._writer_instances.clear()
