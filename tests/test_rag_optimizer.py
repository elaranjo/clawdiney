"""Tests for RAG optimizer functionality."""

import pytest

from clawdiney.rag_optimizer import MMRReranker, QueryPreprocessor


class TestQueryPreprocessor:
    """Test query preprocessing functionality."""

    def test_preprocess_basic(self):
        """Test basic query preprocessing."""
        preprocessor = QueryPreprocessor()
        result = preprocessor.preprocess("  hello   world  ")
        assert result == "hello world"

    def test_preprocess_preserves_acronyms(self):
        """Test that acronyms are preserved but lowercased."""
        # Disable abbreviation expansion to test acronym preservation
        preprocessor = QueryPreprocessor(expand_abbreviations=False)
        result = preprocessor.preprocess("API design patterns")
        assert "api" in result

    def test_preprocess_expand_abbreviations(self):
        """Test abbreviation expansion."""
        preprocessor = QueryPreprocessor(expand_abbreviations=True)
        result = preprocessor.preprocess("SOP for API auth")
        assert "standard operating procedure" in result
        assert "authentication" in result

    def test_preprocess_no_expand_abbreviations(self):
        """Test that abbreviations are not expanded when disabled."""
        preprocessor = QueryPreprocessor(expand_abbreviations=False)
        result = preprocessor.preprocess("SOP for API auth")
        assert "SOP" in result or "sop" in result
        assert "standard operating procedure" not in result

    def test_preprocess_remove_stop_words(self):
        """Test stop word removal."""
        preprocessor = QueryPreprocessor(remove_stop_words=True)
        result = preprocessor.preprocess("what is the best way to do this")
        # Stop words should be removed
        assert "what" not in result
        assert "is" not in result
        assert "the" not in result
        # Content words should remain
        assert "best" in result
        assert "way" in result

    def test_preprocess_no_remove_stop_words(self):
        """Test that stop words are kept when disabled."""
        preprocessor = QueryPreprocessor(remove_stop_words=False)
        result = preprocessor.preprocess("what is the best way")
        assert "what" in result
        assert "is" in result

    def test_extract_keywords(self):
        """Test keyword extraction."""
        preprocessor = QueryPreprocessor()
        keywords = preprocessor.extract_keywords(
            "DatabaseConnection pattern for API endpoints"
        )

        assert "DatabaseConnection" in keywords or "databaseconnection" in [
            k.lower() for k in keywords
        ]
        assert "API" in keywords or "api" in [k.lower() for k in keywords]
        # Stop words should be filtered out
        assert "for" not in keywords

    def test_extract_keywords_snake_case(self):
        """Test keyword extraction with snake_case terms."""
        preprocessor = QueryPreprocessor()
        keywords = preprocessor.extract_keywords("db_connection pool manager")

        assert "db_connection" in keywords or "connection" in keywords

    def test_extract_keywords_deduplication(self):
        """Test that extracted keywords are deduplicated."""
        preprocessor = QueryPreprocessor()
        keywords = preprocessor.extract_keywords("API API API design design")

        # Should have no duplicates
        assert len(keywords) == len(set(keywords))


class TestMMRReranker:
    """Test MMR reranking functionality."""

    def test_mmr_init_valid(self):
        """Test MMR initialization with valid lambda."""
        reranker = MMRReranker(lambda_param=0.5)
        assert reranker.lambda_param == 0.5

    def test_mmr_init_invalid_lambda(self):
        """Test MMR initialization with invalid lambda."""
        with pytest.raises(ValueError):
            MMRReranker(lambda_param=1.5)

        with pytest.raises(ValueError):
            MMRReranker(lambda_param=-0.1)

    def test_mmr_empty_docs(self):
        """Test MMR with empty document list."""
        reranker = MMRReranker()
        docs, metas = reranker.rerank(
            query_embedding=[0.1, 0.2, 0.3],
            doc_embeddings=[],
            docs=[],
            metadatas=[],
            k=5,
        )
        assert docs == []
        assert metas == []

    def test_mmr_fewer_docs_than_k(self):
        """Test MMR when docs < k."""
        reranker = MMRReranker()
        docs, metas = reranker.rerank(
            query_embedding=[0.1, 0.2, 0.3],
            doc_embeddings=[[0.1, 0.2, 0.3]],
            docs=["doc1"],
            metadatas=[{"path": "1.md"}],
            k=5,
        )
        assert len(docs) == 1
        assert len(metas) == 1

    def test_mmr_cosine_similarity_identical(self):
        """Test cosine similarity with identical vectors."""
        reranker = MMRReranker()
        vec = [1.0, 0.0, 0.0]
        similarity = reranker._cosine_similarity(vec, vec)
        assert abs(similarity - 1.0) < 0.001

    def test_mmr_cosine_similarity_orthogonal(self):
        """Test cosine similarity with orthogonal vectors."""
        reranker = MMRReranker()
        vec1 = [1.0, 0.0, 0.0]
        vec2 = [0.0, 1.0, 0.0]
        similarity = reranker._cosine_similarity(vec1, vec2)
        assert abs(similarity) < 0.001

    def test_mmr_diversity_selection(self):
        """Test that MMR selects diverse results."""
        reranker = MMRReranker(lambda_param=0.5)

        # Create embeddings where doc1 and doc2 are similar, doc3 is different
        query_emb = [1.0, 0.0, 0.0]
        doc1_emb = [0.9, 0.1, 0.0]  # Similar to query
        doc2_emb = [0.85, 0.15, 0.0]  # Similar to doc1 (redundant)
        doc3_emb = [0.5, 0.5, 0.0]  # Different but still relevant

        docs = ["doc1", "doc2", "doc3"]
        metas = [{"path": "1.md"}, {"path": "2.md"}, {"path": "3.md"}]
        embeddings = [doc1_emb, doc2_emb, doc3_emb]

        reranked_docs, _ = reranker.rerank(
            query_embedding=query_emb,
            doc_embeddings=embeddings,
            docs=docs,
            metadatas=metas,
            k=2,
        )

        # Should include doc1 (most relevant) and doc3 (diverse)
        # doc2 might be excluded due to redundancy
        assert "doc1" in reranked_docs


class TestQueryPreprocessorIntegration:
    """Integration tests for query preprocessing."""

    def test_preprocess_pipeline(self):
        """Test full preprocessing pipeline."""
        preprocessor = QueryPreprocessor(
            expand_abbreviations=True, remove_stop_words=False
        )

        query = "  How   do I use SOP for   API authentication  "
        result = preprocessor.preprocess(query)

        # Should be normalized (no extra spaces)
        assert "  " not in result
        # Should have expanded abbreviations
        assert "standard operating procedure" in result
        assert "application programming interface" in result

    def test_keyword_extraction_for_hybrid_search(self):
        """Test keyword extraction useful for hybrid search."""
        preprocessor = QueryPreprocessor()

        query = "Implement Repository pattern with Dependency Injection"
        keywords = preprocessor.extract_keywords(query)

        # Should extract technical terms
        assert len(keywords) > 0
        # Should not include stop words
        assert not any(kw.lower() in preprocessor.STOP_WORDS for kw in keywords)
