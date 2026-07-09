"""
Hybrid query engine over the embedded SQLite store.

Retrieval pipeline:
  BM25 (FTS5) + vector KNN (sqlite-vec) -> RRF fusion (k=60)
  -> dedup by note -> optional cross-encoder rerank -> context briefing.
"""

import logging
from pathlib import Path
from typing import Any, TypedDict

from .chunking import Chunk, markdown_chunking
from .config import Config
from .constants import (
    RRF_K,
    SEARCH_EXPAND_GRAPH_DEFAULT,
    SEARCH_N_RESULTS_DEFAULT,
    SEARCH_USE_RERANK_DEFAULT,
)
from .embedding_providers import EmbeddingProvider, default_provider
from .logging_config import setup_logging
from .rag_optimizer import QueryPreprocessor
from .reranker import get_reranker
from .storage import BrainStorage, get_storage
from .vault_config import VaultConfig, load_vault_config

logger = logging.getLogger(__name__)


class Candidate(TypedDict):
    """Represents a note candidate with path and relevance score."""

    path: str
    filename: str
    score: int


class Note(TypedDict):
    """Represents a resolved note with content."""

    path: str
    filename: str
    content: str


def rrf_fuse(
    ranked_lists: list[list[dict[str, Any]]], k: int = RRF_K
) -> list[dict[str, Any]]:
    """
    Reciprocal Rank Fusion over ranked chunk-row lists.

    score(item) = sum over lists of 1 / (k + rank). Items are identified by
    chunk_id. Returns fused rows, best first.
    """
    scores: dict[int, float] = {}
    rows: dict[int, dict[str, Any]] = {}
    for ranked in ranked_lists:
        for rank, row in enumerate(ranked, start=1):
            chunk_id = row["chunk_id"]
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
            rows.setdefault(chunk_id, row)
    ordered = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [rows[chunk_id] for chunk_id, _score in ordered]


class BrainQueryEngine:
    def __init__(
        self,
        vault: str | None = None,
        storage: BrainStorage | None = None,
        provider: EmbeddingProvider | None = None,
    ):
        self.current_vault = vault or Config.get_default_vault()

        vault_path = Config.get_vault_path(self.current_vault)
        self.vault_root = Path(vault_path).expanduser().resolve()

        self.vault_config: VaultConfig | None = None
        try:
            if self.vault_root.joinpath("clawdiney.toml").exists():
                self.vault_config = load_vault_config(self.vault_root)
        except Exception as exc:
            logger.warning(
                "Failed to load vault config from %s: %s", self.vault_root, exc
            )

        self.storage = storage or get_storage()
        self.provider = provider or default_provider()
        self.query_preprocessor = QueryPreprocessor(
            expand_abbreviations=True, remove_stop_words=False
        )

    def close(self) -> None:
        """Close storage connections owned by this thread."""
        self.storage.close()

    def __enter__(self) -> "BrainQueryEngine":
        """Enter context manager, returning the engine instance."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit context manager, closing storage connections."""
        self.close()

    def get_embedding(self, text: str) -> list[float]:
        """Embed text through the configured provider (retry inside provider)."""
        return self.provider.embed(text)

    # ------------------------------------------------------------------
    # Note resolution / local file access
    # ------------------------------------------------------------------

    def _normalize_note_path(self, note_path: str) -> str:
        """Return a canonical vault-relative path and ensure it stays inside the vault."""
        raw_path = Path(note_path).expanduser()
        if raw_path.is_absolute():
            resolved = raw_path.resolve()
        else:
            resolved = (self.vault_root / raw_path).resolve()

        try:
            return resolved.relative_to(self.vault_root).as_posix()
        except ValueError as exc:
            raise ValueError(
                f"Path '{note_path}' is outside the configured vault"
            ) from exc

    def _resolve_note_path(self, note_path: str) -> tuple[Path, str]:
        relative_path = self._normalize_note_path(note_path)
        absolute_path = self.vault_root / relative_path
        if not absolute_path.is_file():
            raise FileNotFoundError(f"Note not found: {relative_path}")
        return absolute_path, relative_path

    def _split_note_into_chunks(self, content: str) -> list[Chunk]:
        """Split markdown text by headers for local note inspection."""
        return markdown_chunking(content)

    def resolve_note(self, name: str, vault: str | None = None) -> list[Candidate]:
        """Return candidate notes that match a basename or relative path fragment."""
        query = name.strip().lower()
        if not query:
            return []

        vault_root = (
            Path(Config.get_vault_path(vault)).expanduser().resolve()
            if vault is not None
            else self.vault_root
        )

        candidates: list[Candidate] = []
        for file_path in vault_root.rglob("*.md"):
            relative_path = file_path.relative_to(vault_root).as_posix()
            filename = file_path.name
            filename_lower = filename.lower()
            relative_lower = relative_path.lower()

            score: int | None = None
            if filename_lower == query or relative_lower == query:
                score = 0
            elif relative_lower.endswith(f"/{query}"):
                score = 1
            elif filename_lower.startswith(query):
                score = 2
            elif query in filename_lower:
                score = 3
            elif query in relative_lower:
                score = 4

            if score is None:
                continue

            candidates.append(
                {
                    "path": relative_path,
                    "filename": filename,
                    "score": score,
                }
            )

        candidates.sort(key=lambda item: (item["score"], item["path"]))
        return candidates

    def get_note_by_path(self, path: str, vault: str | None = None) -> Note:
        vault_root = (
            Path(Config.get_vault_path(vault)).expanduser().resolve()
            if vault is not None
            else self.vault_root
        )
        abs_path = Path(path).expanduser()
        if abs_path.is_absolute():
            resolved = abs_path.resolve()
        else:
            resolved = (vault_root / path).resolve()

        try:
            relative_path = resolved.relative_to(vault_root).as_posix()
        except ValueError as exc:
            raise ValueError(f"Path '{path}' is outside the vault") from exc

        if not resolved.is_file():
            raise FileNotFoundError(f"Note not found: {relative_path}")

        return {
            "path": relative_path,
            "filename": resolved.name,
            "content": resolved.read_text(encoding="utf-8"),
        }

    def read_source(self, source_path: str, vault: str | None = None) -> str:
        return self.get_note_by_path(source_path, vault=vault)["content"]

    def get_note_chunks(self, filename: str) -> list[dict[str, Any]]:
        candidates = self.resolve_note(filename)
        if not candidates:
            raise FileNotFoundError(f"No notes found for '{filename}'")
        if len(candidates) > 1 and candidates[0]["path"] != filename:
            candidate_paths = ", ".join(
                candidate["path"] for candidate in candidates[:10]
            )
            raise ValueError(
                f"Multiple notes match '{filename}'. Resolve a canonical path first: {candidate_paths}"
            )

        note = self.get_note_by_path(candidates[0]["path"])
        chunks = self._split_note_into_chunks(note["content"])
        return [
            {
                "path": note["path"],
                "filename": note["filename"],
                "header": chunk["header"],
                "content": chunk["content"],
                "chunk_index": index,
            }
            for index, chunk in enumerate(chunks)
        ]

    # ------------------------------------------------------------------
    # Graph
    # ------------------------------------------------------------------

    def get_related_notes(self, note_ref: str, vault: str | None = None) -> list[str]:
        """Notes linked to note_ref via WikiLinks (either direction) or shared tags."""
        vault_name = vault or self.current_vault
        return self.storage.get_related_notes(note_ref, vault_name)

    # ------------------------------------------------------------------
    # Hybrid search
    # ------------------------------------------------------------------

    def _get_fallback_chain(self) -> list[str]:
        chain: list[str] = [self.current_vault]
        if self.vault_config:
            for lv in self.vault_config.linked_vaults:
                if lv not in chain:
                    chain.append(lv)
        if "general" not in chain:
            chain.append("general")
        return chain

    def _hybrid_retrieve(
        self, query: str, vaults: list[str], n_results: int, mode: str = "hybrid"
    ) -> list[dict[str, Any]]:
        """BM25 and/or vector retrieval fused with RRF. Fail-soft per retriever.

        mode: "hybrid" (both retrievers, default), "bm25" (BM25 only,
        skips the embedding call), or "vector" (vector KNN only).
        """
        fetch_k = n_results * 3

        bm25_rows: list[dict[str, Any]] = []
        if mode in ("hybrid", "bm25"):
            try:
                bm25_rows = self.storage.search_bm25(query, vaults, fetch_k)
            except Exception as exc:
                logger.warning("BM25 retrieval failed: %s", exc)

        vector_rows: list[dict[str, Any]] = []
        if mode in ("hybrid", "vector"):
            try:
                embedding = self.get_embedding(query)
                vector_rows = self.storage.search_vectors(embedding, vaults, fetch_k)
            except Exception as exc:
                logger.warning("Vector retrieval failed: %s", exc)

        return rrf_fuse([bm25_rows, vector_rows])

    @staticmethod
    def _dedupe_by_note(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Keep only the best-ranked chunk per note path."""
        seen: set[tuple[str, str]] = set()
        unique: list[dict[str, Any]] = []
        for row in rows:
            key = (row["vault"], row["path"])
            if key not in seen:
                seen.add(key)
                unique.append(row)
        return unique

    def retrieve(
        self,
        text: str,
        n_results: int = SEARCH_N_RESULTS_DEFAULT,
        use_rerank: bool = SEARCH_USE_RERANK_DEFAULT,
        mode: str = "hybrid",
        vault_override: str | None = None,
    ) -> list[dict[str, Any]]:
        """Retrieve ranked, deduped (and optionally reranked) chunk rows.

        Structured counterpart to `query()` for callers (e.g. the eval
        harness) that need candidate rows rather than a formatted briefing.
        mode: "hybrid" (default), "bm25", or "vector" — see `_hybrid_retrieve`.
        """
        processed_query = self.query_preprocessor.preprocess(text)
        if processed_query != text and logger.isEnabledFor(logging.DEBUG):
            logger.debug("Query preprocessed: '%s' -> '%s'", text, processed_query)

        fallback_chain = self._get_fallback_chain()
        if vault_override and vault_override not in fallback_chain:
            fallback_chain = [vault_override] + [
                v for v in fallback_chain if v != vault_override
            ]

        rows = self._hybrid_retrieve(
            processed_query, fallback_chain, n_results, mode=mode
        )
        rows = self._dedupe_by_note(rows)

        if use_rerank and Config.ENABLE_RERANK and rows:
            pairs = [(row["content"], row) for row in rows]
            reranked = get_reranker().rerank(processed_query, pairs)
            rows = [meta for _doc, meta in reranked]

        return rows[:n_results]

    def query(
        self,
        text: str,
        n_results: int = SEARCH_N_RESULTS_DEFAULT,
        expand_graph: bool = SEARCH_EXPAND_GRAPH_DEFAULT,
        use_rerank: bool = SEARCH_USE_RERANK_DEFAULT,
        vault_override: str | None = None,
    ) -> str:
        rows = self.retrieve(
            text,
            n_results=n_results,
            use_rerank=use_rerank,
            vault_override=vault_override,
        )
        return self._build_context(rows, expand_graph)

    def _build_context(self, rows: list[dict[str, Any]], expand_graph: bool) -> str:
        context_briefing = []
        seen_notes = set()

        for row in rows:
            note_label = row["path"]
            vault_source = row.get("vault", "?")
            context_briefing.append(
                f"--- Source [{vault_source}]: {note_label} ---\n{row['content']}"
            )
            seen_notes.add(note_label)

            if expand_graph:
                related = self.get_related_notes(note_label, vault=vault_source)
                for rel_note in related:
                    if rel_note not in seen_notes:
                        context_briefing.append(
                            f"--- Related Note: {rel_note} (Linked via {note_label}) ---"
                        )
                        seen_notes.add(rel_note)

        return "\n\n".join(context_briefing)


if __name__ == "__main__":
    import sys

    setup_logging()

    if len(sys.argv) < 2:
        logger.error("Usage: python query_engine.py 'your search query'")
        sys.exit(1)

    query_text = " ".join(sys.argv[1:])

    # Use context manager for automatic cleanup
    with BrainQueryEngine() as engine:
        briefing = engine.query(query_text)
        logger.info("Query completed successfully")
        print(
            f"\n=== BRAIN CONTEXT BRIEFING ===\n\n{briefing}\n\n=============================="
        )
