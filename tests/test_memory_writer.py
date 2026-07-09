"""memory_writer tests: fact normalization and write_memory write path."""

import pytest

from clawdiney.memory_writer import (
    MEMORY_DIR,
    normalize_fact,
    write_memory,
)
from clawdiney.query_engine import BrainQueryEngine
from clawdiney.storage import BrainStorage
from clawdiney.vault_writer import VaultWriter

DIM = 4


class FakeProvider:
    """Deterministic embeddings by text length, so equal-length subjects collide
    (used to exercise entity-resolution reuse in tests)."""

    def embed(self, text: str) -> list[float]:
        seed = float(len(text) % 97)
        return [seed, seed / 2, seed / 3, seed / 4]

    def embed_batch(self, texts):
        return [self.embed(t) for t in texts]


class TestNormalizeFact:
    def test_matches_subject_verb_value(self):
        result = normalize_fact("User prefers embedded SQLite over Docker-based stacks")
        assert result.subject == "User"
        assert result.predicate == "prefers"
        assert result.value == "embedded SQLite over Docker-based stacks"
        assert result.confidence == 1.0

    def test_matches_multiword_verb(self):
        result = normalize_fact("Alice works on the clawdiney project")
        assert result.subject == "Alice"
        assert result.predicate == "works on"
        assert result.value == "the clawdiney project"

    def test_strips_trailing_period(self):
        result = normalize_fact("Bob likes tabs over spaces.")
        assert result.value == "tabs over spaces"

    def test_fallback_when_no_known_verb(self):
        result = normalize_fact("something something happened yesterday at noon")
        assert result.predicate == "mentions"
        assert result.confidence == 0.4
        assert result.value == "something something happened yesterday at noon"

    def test_empty_fact(self):
        result = normalize_fact("   ")
        assert result.subject == "" and result.confidence == 0.0


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


class TestWriteMemory:
    def test_explicit_write_creates_note(self, storage, writer):
        result = write_memory(
            "User prefers embedded SQLite over Docker-based stacks",
            source="conversation",
            storage=storage,
            writer=writer,
            provider=FakeProvider(),
        )
        assert result.success
        assert result.path == f"{MEMORY_DIR}/User.md"
        note = (writer.vault_root / result.path).read_text(encoding="utf-8")
        assert "source: agent" in note
        assert "**prefers**: embedded SQLite over Docker-based stacks" in note

    def test_duplicate_write_is_noop(self, storage, writer):
        fact = "User prefers embedded SQLite over Docker-based stacks"
        first = write_memory(
            fact,
            source="conversation",
            storage=storage,
            writer=writer,
            provider=FakeProvider(),
        )
        note_before = (writer.vault_root / first.path).read_text(encoding="utf-8")

        second = write_memory(
            fact,
            source="conversation",
            storage=storage,
            writer=writer,
            provider=FakeProvider(),
        )
        note_after = (writer.vault_root / first.path).read_text(encoding="utf-8")

        assert second.success
        assert "no-op" in second.message
        assert note_before == note_after

    def test_updated_value_replaces_bullet(self, storage, writer):
        write_memory(
            "User prefers embedded SQLite over Docker-based stacks",
            source="conversation",
            storage=storage,
            writer=writer,
            provider=FakeProvider(),
        )
        result = write_memory(
            "User prefers Postgres over embedded SQLite",
            source="conversation",
            storage=storage,
            writer=writer,
            provider=FakeProvider(),
        )
        note = (writer.vault_root / result.path).read_text(encoding="utf-8")

        assert result.success
        assert "Fact updated" in result.message
        assert note.count("**prefers**:") == 1
        assert "Postgres over embedded SQLite" in note
        assert "embedded SQLite over Docker-based stacks" not in note

    def test_low_confidence_fact_rejected(self, storage, writer):
        result = write_memory(
            "something something happened yesterday at noon",
            source="conversation",
            storage=storage,
            writer=writer,
            provider=FakeProvider(),
            min_confidence=0.5,
        )
        assert not result.success
        assert "below the minimum" in result.message
        assert not (writer.vault_root / MEMORY_DIR).exists()

    def test_empty_fact_rejected(self, storage, writer):
        result = write_memory(
            "   ",
            source="conversation",
            storage=storage,
            writer=writer,
            provider=FakeProvider(),
        )
        assert not result.success

    def test_resolves_to_existing_entity_note(self, storage, writer):
        write_memory(
            "Marcus prefers dark mode",
            source="conversation",
            storage=storage,
            writer=writer,
            provider=FakeProvider(),
        )
        # "Markos" has the same length as "Marcus" -> FakeProvider embeds it
        # identically, so entity resolution should reuse the "Marcus" entity
        # instead of creating a second note.
        result = write_memory(
            "Markos has a new laptop",
            source="conversation",
            storage=storage,
            writer=writer,
            provider=FakeProvider(),
        )
        assert result.subject == "Marcus"
        assert result.path == f"{MEMORY_DIR}/Marcus.md"
        note = (writer.vault_root / result.path).read_text(encoding="utf-8")
        assert "**prefers**: dark mode" in note
        assert "**has**: a new laptop" in note


class TestNoWriteSideEffectsOnReadPath:
    def test_query_does_not_touch_memory_dir(self, tmp_path, storage, monkeypatch):
        vault_root = tmp_path / "vault"
        vault_root.mkdir()
        monkeypatch.delenv("VAULTS_DIR", raising=False)
        monkeypatch.delenv("VAULTS", raising=False)
        monkeypatch.setattr("clawdiney.config.Config.VAULT_PATH", str(vault_root))
        engine = BrainQueryEngine(
            vault="default", storage=storage, provider=FakeProvider()
        )
        storage.upsert_note(
            vault="default",
            path="note.md",
            content_hash="h",
            updated_at="now",
            chunks=[{"header": "", "content": "some content about testing"}],
            embeddings=[[1.0, 2.0, 3.0, 4.0]],
            wikilinks=[],
            tags=[],
        )
        engine.query("testing", expand_graph=False)
        engine.close()
        assert not (vault_root / MEMORY_DIR).exists()
