"""
Integration and load tests for Clawdiney.

These tests verify end-to-end functionality and performance
with realistic vault sizes.
"""
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock

import pytest

from brain_indexer import (
    build_note_record,
    chunk_text,
    extract_wikilinks,
    index_vault,
)
from chunking import Chunk
from config import Config


class TestChunkingIntegration:
    """Integration tests for chunking strategies."""

    def test_markdown_chunking_preserves_headers(self):
        """Verify markdown chunking correctly splits by headers."""
        content = """# Introduction
This is the intro.

# Main Section
Some content here.

## Subsection
More details.

# Conclusion
Final thoughts.
"""
        chunks = chunk_text(content, strategy="headers")

        assert len(chunks) >= 3
        headers = [chunk["header"] for chunk in chunks]
        assert "Introduction" in headers
        assert "Main Section" in headers
        assert "Conclusion" in headers

    def test_fixed_size_chunking_with_overlap(self):
        """Verify fixed-size chunking creates proper overlaps."""
        content = "A" * 1000  # 1000 characters

        chunks = chunk_text(
            content, strategy="fixed", chunk_size=300, overlap=50
        )

        assert len(chunks) >= 4  # 1000/300 = 3.33, so at least 4 chunks
        assert all(len(chunk["content"]) > 0 for chunk in chunks)

    def test_semantic_chunking_respects_sentences(self):
        """Verify semantic chunking doesn't break sentences."""
        content = (
            "First sentence. Second sentence. Third sentence. "
            "Fourth sentence. Fifth sentence."
        )

        chunks = chunk_text(content, strategy="semantic", chunk_size=50)

        # Each chunk should contain complete sentences
        for chunk in chunks:
            text = chunk["content"]
            # If there's a period, it should be at the end or followed by space
            if "." in text and not text.endswith("."):
                assert ". " in text  # Sentence continues


class TestWikilinkExtraction:
    """Tests for wikilink extraction functionality."""

    def test_extract_wikilinks_simple(self):
        """Test basic wikilink extraction."""
        content = "Check out [[Design Patterns]] for more info."
        links = extract_wikilinks(content)
        assert links == ["Design Patterns"]

    def test_extract_wikilinks_multiple(self):
        """Test extraction of multiple wikilinks."""
        content = """
        See [[Architecture]] and [[Best Practices]].
        Also check [[Getting Started]] for basics.
        """
        links = extract_wikilinks(content)
        assert len(links) == 3
        assert "Architecture" in links
        assert "Best Practices" in links
        assert "Getting Started" in links

    def test_extract_wikilinks_with_paths(self):
        """Test extraction of wikilinks with paths."""
        content = "Refer to [[docs/architecture]] for details."
        links = extract_wikilinks(content)
        assert links == ["docs/architecture"]

    def test_extract_wikilinks_empty(self):
        """Test extraction when no wikilinks present."""
        content = "No links in this content."
        links = extract_wikilinks(content)
        assert links == []


class TestNoteRecordBuilder:
    """Tests for note record building."""

    def test_build_note_record_complete(self):
        """Test building a complete note record."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "test.md"
            test_file.write_text(
                "# Test Note\n\nContent here.\n\n[[Linked Note]]\n\n#tag"
            )

            record = build_note_record(
                test_file, Path(tmpdir), strategy="headers"
            )

            assert record is not None
            assert record["name"] == "test.md"
            assert record["path"] == "test.md"
            assert "#tag" in record["content"]
            assert ["tag"] == record["tags"]
            assert ["Linked Note"] == record["wikilinks"]
            assert len(record["chunks"]) >= 1

    def test_build_note_record_empty_file(self):
        """Test building record from empty file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            test_file = Path(tmpdir) / "empty.md"
            test_file.write_text("")

            record = build_note_record(test_file, Path(tmpdir))

            assert record is None


class TestIndexingPerformance:
    """Performance tests for indexing operations."""

    @pytest.fixture
    def large_vault(self):
        """Create a synthetic vault with 100 notes for performance testing."""
        tmpdir = tempfile.mkdtemp()
        vault_path = Path(tmpdir)

        # Create 100 notes with varying sizes
        for i in range(100):
            note_file = vault_path / f"note_{i:03d}.md"
            content = f"""# Note {i}

This is note number {i} in the test vault.

## Section 1
Lorem ipsum dolor sit amet, consectetur adipiscing elit.
Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.

## Section 2
Ut enim ad minim veniam, quis nostrud exercitation ullamco.
"""
            # Add some wikilinks
            if i > 0:
                content += f"\n\nSee also [[note_{i-1:03d}]]\n"

            # Add some tags
            content += f"\n\n#test #note-{i % 10}\n"

            note_file.write_text(content)

        yield vault_path

        # Cleanup
        shutil.rmtree(tmpdir)

    def test_indexing_performance(self, large_vault, monkeypatch):
        """Test indexing performance with 100 notes."""
        # Mock ChromaDB and Neo4j to measure pure indexing performance
        mock_collection = Mock()
        mock_driver = Mock()
        mock_session = Mock()
        mock_driver.session.return_value.__enter__ = Mock(
            return_value=mock_session
        )
        mock_driver.session.return_value.__exit__ = Mock(
            return_value=None
        )

        start_time = time.time()

        # Index the vault
        summary = index_vault(
            vault_root=large_vault,
            collection=mock_collection,
            neo4j_driver=mock_driver,
            strategy="headers",
        )

        elapsed = time.time() - start_time

        # Assertions
        assert summary["total_files"] == 100
        assert summary["processed_files"] == 100
        assert summary["indexed_chunks"] > 100  # At least 1 chunk per note

        # Performance threshold: should index 100 notes in < 5 seconds
        # (excluding embedding generation which is mocked)
        assert elapsed < 5.0, f"Indexing took {elapsed:.2f}s (threshold: 5s)"

        print(
            f"\nPerformance: Indexed {summary['total_files']} notes "
            f"({summary['indexed_chunks']} chunks) in {elapsed:.2f}s"
        )


class TestChunkingPerformance:
    """Performance tests for chunking operations."""

    def test_chunking_large_document(self):
        """Test chunking performance with large document."""
        # Create a 50KB document
        large_content = "Lorem ipsum dolor sit amet. " * 2000

        start_time = time.time()

        chunks = chunk_text(large_content, strategy="headers")

        elapsed = time.time() - start_time

        # Should complete in < 0.5 seconds
        assert elapsed < 0.5, f"Chunking took {elapsed:.2f}s (threshold: 0.5s)"
        assert len(chunks) > 0
        assert sum(len(c["content"]) for c in chunks) > 0

        print(
            f"\nPerformance: Chunked {len(large_content)} chars "
            f"into {len(chunks)} chunks in {elapsed:.3f}s"
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
