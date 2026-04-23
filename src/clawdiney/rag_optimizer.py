"""RAG optimization utilities for better retrieval quality."""

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# MMR configuration constants
MMR_LAMBDA_DEFAULT = 0.7  # Balance: 70% relevance, 30% diversity
MMR_LAMBDA_MIN = 0.0
MMR_LAMBDA_MAX = 1.0

# Query preprocessing limits
MAX_QUERY_LENGTH = 500  # Prevent regex DoS


class QueryPreprocessor:
    """
    Preprocess search queries for better retrieval.

    Improves query quality by:
    - Normalizing whitespace and casing
    - Expanding common abbreviations
    - Extracting key technical terms
    - Removing stop words that don't add semantic value
    """

    # Common technical abbreviations to expand
    ABBREVIATIONS = {
        "SOP": "standard operating procedure",
        "API": "application programming interface",
        "DB": "database",
        "SQL": "structured query language",
        "HTTP": "hypertext transfer protocol",
        "JSON": "javascript object notation",
        "UI": "user interface",
        "UX": "user experience",
        "ID": "identifier",
        "auth": "authentication",
        "config": "configuration",
        "env": "environment",
        "prod": "production",
        "dev": "development",
        "staging": "staging environment",
    }

    # Stop words that don't add semantic value for code/tech queries
    STOP_WORDS = {
        "what",
        "is",
        "are",
        "the",
        "a",
        "an",
        "how",
        "do",
        "does",
        "can",
        "i",
        "we",
        "you",
        "they",
        "it",
        "this",
        "that",
        "these",
        "those",
        "for",
        "to",
        "of",
        "in",
        "on",
        "with",
        "about",
        "from",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "all",
        "each",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "and",
        "but",
        "if",
        "or",
        "because",
        "until",
        "while",
        "although",
        "though",
        "as",
        "at",
        "by",
        "get",
        "got",
        "getting",
        "make",
        "made",
        "making",
        "take",
        "took",
        "taking",
        "use",
        "used",
        "using",
        "work",
        "worked",
        "working",
    }

    def __init__(self, expand_abbreviations: bool = True, remove_stop_words: bool = False):
        """
        Initialize the query preprocessor.

        Args:
            expand_abbreviations: Whether to expand common abbreviations
            remove_stop_words: Whether to remove stop words (use with caution)
        """
        self.expand_abbreviations = expand_abbreviations
        self.remove_stop_words = remove_stop_words

    def preprocess(self, query: str) -> str:
        """
        Preprocess a search query.

        Args:
            query: Original search query

        Returns:
            Preprocessed query optimized for semantic search
        """
        # 1. Normalize whitespace
        processed = " ".join(query.split())

        # 2. Normalize casing (preserve acronyms)
        processed = self._normalize_casing(processed)

        # 3. Expand abbreviations
        if self.expand_abbreviations:
            processed = self._expand_abbreviations(processed)

        # 4. Remove stop words (optional - can hurt query intent)
        if self.remove_stop_words:
            processed = self._remove_stop_words(processed)

        # 5. Clean up extra spaces
        processed = " ".join(processed.split())

        return processed

    def _normalize_casing(self, text: str) -> str:
        """
        Normalize casing while preserving acronyms and proper nouns.

        Keeps ALL CAPS words (acronyms) and Title Case (proper nouns) intact.
        """
        words = text.split()
        normalized = []

        for word in words:
            # Preserve acronyms (all caps) and proper nouns (title case)
            if word.isupper() or word.istitle():
                normalized.append(word.lower())
            else:
                normalized.append(word.lower())

        return " ".join(normalized)

    def _expand_abbreviations(self, text: str) -> str:
        """Expand common technical abbreviations."""
        words = text.split()
        expanded = []

        for word in words:
            # Check exact match
            if word in self.ABBREVIATIONS:
                expanded.append(self.ABBREVIATIONS[word])
            # Check case-insensitive match
            elif word.lower() in {k.lower() for k in self.ABBREVIATIONS.keys()}:
                for key, value in self.ABBREVIATIONS.items():
                    if key.lower() == word.lower():
                        expanded.append(value)
                        break
            else:
                expanded.append(word)

        return " ".join(expanded)

    def _remove_stop_words(self, text: str) -> str:
        """Remove common stop words from query."""
        words = text.split()
        filtered = [word for word in words if word.lower() not in self.STOP_WORDS]
        return " ".join(filtered)

    def extract_keywords(self, query: str) -> list[str]:
        """
        Extract key technical terms from query.

        Useful for hybrid search (semantic + keyword).

        Args:
            query: Search query (max 500 chars)

        Returns:
            List of keywords extracted from query
        """
        # Truncate query to prevent regex DoS
        query = query[:MAX_QUERY_LENGTH]

        # Pattern for technical terms: camelCase, snake_case, or multi-word phrases
        patterns = [
            r"\b[A-Z][a-z]+(?:[A-Z][a-z]+)+\b",  # camelCase like "DatabaseConnection"
            r"\b[a-z]+(?:_[a-z]+)+\b",  # snake_case like "db_connection"
            r"\b[A-Z]{2,}\b",  # Acronyms like "API", "HTTP"
            r"\b[a-zA-Z]+\b",  # Regular words
        ]

        keywords = []
        for pattern in patterns:
            matches = re.findall(pattern, query)
            keywords.extend(matches)

        # Filter out stop words
        keywords = [
            kw for kw in keywords if kw.lower() not in self.STOP_WORDS and len(kw) > 2
        ]

        return list(set(keywords))  # Deduplicate


class MMRReranker:
    """
    Maximal Marginal Relevance reranking.

    Balances relevance with diversity to avoid redundant results.
    Useful when multiple chunks from the same note would be returned.

    Reference: Carbonell & Goldstein (1998) - "The Use of MMR, Diversity-Based
    Reranking for Reordering Documents and Producing Summaries"
    """

    def __init__(self, lambda_param: float = MMR_LAMBDA_DEFAULT):
        """
        Initialize MMR reranker.

        Args:
            lambda_param: Balance between relevance and diversity.
                         1.0 = pure relevance (no diversity)
                         0.0 = pure diversity (no relevance)
                         0.7 = good balance (default)
        """
        if not MMR_LAMBDA_MIN <= lambda_param <= MMR_LAMBDA_MAX:
            raise ValueError(
                f"lambda_param must be between {MMR_LAMBDA_MIN} and {MMR_LAMBDA_MAX}"
            )
        self.lambda_param = lambda_param

    def rerank(
        self,
        query_embedding: list[float],
        doc_embeddings: list[list[float]],
        docs: list[str],
        metadatas: list[dict[str, Any]],
        k: int = 5,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """
        Rerank documents using MMR.

        Args:
            query_embedding: Query embedding vector
            doc_embeddings: List of document embedding vectors
            docs: List of document contents
            metadatas: List of metadata dicts
            k: Number of results to return

        Returns:
            Tuple of (reranked_docs, reranked_metadatas)
        """
        if not docs or not doc_embeddings:
            return [], []

        n_docs = len(docs)
        k = min(k, n_docs)

        # Precompute query similarities
        query_similarities = self._compute_query_similarities(
            query_embedding, doc_embeddings
        )

        # Select documents using MMR
        selected_indices = self._select_mmr_indices(
            doc_embeddings, query_similarities, k
        )

        # Return reranked results
        reranked_docs = [docs[i] for i in selected_indices]
        reranked_metadatas = [metadatas[i] for i in selected_indices]

        return reranked_docs, reranked_metadatas

    def _compute_query_similarities(
        self, query_embedding: list[float], doc_embeddings: list[list[float]]
    ) -> list[float]:
        """
        Compute similarity between query and all document embeddings.

        Args:
            query_embedding: Query embedding vector
            doc_embeddings: List of document embedding vectors

        Returns:
            List of similarity scores
        """
        return [
            self._cosine_similarity(query_embedding, emb)
            for emb in doc_embeddings
        ]

    def _select_mmr_indices(
        self,
        doc_embeddings: list[list[float]],
        query_similarities: list[float],
        k: int,
    ) -> list[int]:
        """
        Select document indices using MMR algorithm.

        Args:
            doc_embeddings: List of document embedding vectors
            query_similarities: Precomputed query similarities
            k: Number of results to select

        Returns:
            List of selected document indices
        """
        n_docs = len(doc_embeddings)
        selected_indices: list[int] = []
        remaining_indices = list(range(n_docs))

        while len(selected_indices) < k and remaining_indices:
            best_idx = self._find_best_mmr_candidate(
                doc_embeddings,
                query_similarities,
                selected_indices,
                remaining_indices,
            )

            if best_idx is not None:
                selected_indices.append(best_idx)
                remaining_indices.remove(best_idx)

        return selected_indices

    def _find_best_mmr_candidate(
        self,
        doc_embeddings: list[list[float]],
        query_similarities: list[float],
        selected_indices: list[int],
        remaining_indices: list[int],
    ) -> int | None:
        """
        Find the best document candidate using MMR scoring.

        Args:
            doc_embeddings: List of document embedding vectors
            query_similarities: Precomputed query similarities
            selected_indices: Already selected document indices
            remaining_indices: Candidate document indices

        Returns:
            Index of best candidate, or None if no candidates
        """
        best_mmr_score = float("-inf")
        best_idx: int | None = None

        for idx in remaining_indices:
            relevance = query_similarities[idx]
            diversity = self._compute_diversity_score(
                doc_embeddings[idx], doc_embeddings, selected_indices
            )

            mmr_score = (
                self.lambda_param * relevance
                - (1 - self.lambda_param) * diversity
            )

            if mmr_score > best_mmr_score:
                best_mmr_score = mmr_score
                best_idx = idx

        return best_idx

    def _compute_diversity_score(
        self,
        doc_embedding: list[float],
        doc_embeddings: list[list[float]],
        selected_indices: list[int],
    ) -> float:
        """
        Compute diversity score as max similarity to already selected docs.

        Args:
            doc_embedding: Document embedding to evaluate
            doc_embeddings: All document embeddings
            selected_indices: Indices of already selected documents

        Returns:
            Maximum similarity to selected documents (0.0 if none selected)
        """
        if not selected_indices:
            return 0.0

        return max(
            self._cosine_similarity(doc_embedding, doc_embeddings[sel])
            for sel in selected_indices
        )

    def _cosine_similarity(self, a: list[float], b: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        dot_product = sum(x * y for x, y in zip(a, b))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(x * x for x in b) ** 0.5

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot_product / (norm_a * norm_b)
