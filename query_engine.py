import logging
import signal
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, TypedDict

import chromadb
import httpx
import ollama
from neo4j import GraphDatabase

from chunking import Chunk, markdown_chunking
from config import Config
from constants import (
    RERANK_BATCH_SIZE,
    RERANK_TIMEOUT_SECONDS,
    SEARCH_EXPAND_GRAPH_DEFAULT,
    SEARCH_N_RESULTS_DEFAULT,
    SEARCH_USE_RERANK_DEFAULT,
)
from logging_config import setup_logging

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


class BrainQueryEngine:
    def __init__(self):
        self.vault_root = Path(Config.VAULT_PATH).expanduser().resolve()

        # ChromaDB Setup - Always use HTTP client
        chroma_config = Config.get_chroma_client_config()
        self.chroma_client = chromadb.HttpClient(
            host=chroma_config["host"], port=chroma_config["port"]
        )
        # Configura timeout para 300 segundos no cliente httpx subjacente
        self.chroma_client.timeout = httpx.Timeout(300.0)
        self.vector_collection = self.chroma_client.get_collection(
            name="obsidian_vault"
        )

        # Neo4j Setup
        self.neo4j_driver = GraphDatabase.driver(
            Config.NEO4J_URI,
            auth=(Config.NEO4J_USER, Config.get_neo4j_password()),
        )

    def close(self) -> None:
        """Close all database connections (Neo4j + ChromaDB)."""
        self.neo4j_driver.close()
        if hasattr(self.chroma_client, "close"):
            self.chroma_client.close()

    def __enter__(self) -> "BrainQueryEngine":
        """Enter context manager, returning the engine instance."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        """Exit context manager, closing all database connections."""
        self.close()

    def get_embedding(self, text: str) -> list[float]:
        response = ollama.embeddings(model=Config.MODEL_NAME, prompt=text)
        return response["embedding"]

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

    def resolve_note(self, name: str) -> list[Candidate]:
        """Return candidate notes that match a basename or relative path fragment."""
        query = name.strip().lower()
        if not query:
            return []

        candidates: list[Candidate] = []
        for file_path in self.vault_root.rglob("*.md"):
            relative_path = file_path.relative_to(self.vault_root).as_posix()
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

    def get_note_by_path(self, path: str) -> Note:
        absolute_path, relative_path = self._resolve_note_path(path)
        return {
            "path": relative_path,
            "filename": absolute_path.name,
            "content": absolute_path.read_text(encoding="utf-8"),
        }

    def read_source(self, source_path: str) -> str:
        return self.get_note_by_path(source_path)["content"]

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

    def get_related_notes(self, note_ref: str) -> list[str]:
        """
        Fetches notes that are linked to the given note in Neo4j, including tag-based relationships.
        """
        with self.neo4j_driver.session() as session:
            query = """
            MATCH (n:Note)-[:LINKS_TO|SHARES_TAG]-(related:Note)
            WHERE n.path = $note_ref OR n.name = $note_ref
            RETURN related.name as name, related.path as path
            """
            result = session.run(query, note_ref=note_ref)
            return [record["path"] or record["name"] for record in result]

    def _score_single_doc(self, query: str, doc: str) -> float | None:
        """Score a single document against query. Returns score or None."""
        combined = f"Output only the relevance score between 0 and 1. Query: {query}\nDocument: {doc}"
        try:
            response = ollama.generate(
                model=Config.RERANK_MODEL_NAME,
                prompt=combined,
                options={"temperature": 0},
            )
            score_str = response.get("response", "").strip()
            try:
                return float(score_str)
            except ValueError:
                logger.warning(f"Invalid score format from reranker: {score_str!r}")
                return None
        except (TimeoutError, FuturesTimeoutError) as e:
            logger.warning(f"Rerank timeout for document: {e}")
            return None
        except (ConnectionError, RuntimeError) as e:
            logger.warning(f"Rerank model error: {e}")
            return None

    def rerank_results(
        self,
        query: str,
        results: list[tuple[str, dict[str, Any]]],
        timeout: int = RERANK_TIMEOUT_SECONDS,
        batch_size: int = RERANK_BATCH_SIZE,
    ) -> list[tuple[str, dict[str, Any]]]:
        """
        Rerank results using cross-encoder model with timeout and batch processing.

        Args:
            query: Search query string
            results: List of (document, metadata) tuples
            timeout: Maximum seconds for entire reranking operation (default: 30s)
            batch_size: Number of documents to process in parallel (default: 5)

        Returns:
            Reranked results sorted by score, or original results if rerank fails/times out.
        """
        if not results:
            return results

        scored_results = []
        successful_scores = 0

        try:
            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                futures = {
                    executor.submit(self._score_single_doc, query, doc): (doc, meta)
                    for doc, meta in results
                }

                # Wait for all futures with global timeout
                def timeout_handler(signum, frame):
                    raise FuturesTimeoutError(f"Rerank exceeded {timeout}s timeout")

                # Set alarm for timeout
                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(timeout)

                try:
                    for future in futures:
                        doc, meta = futures[future]
                        try:
                            score = future.result(timeout=timeout)
                            if score is not None:
                                successful_scores += 1
                            scored_results.append((score, doc, meta))
                        except FuturesTimeoutError:
                            logger.warning("Document scoring timed out")
                            scored_results.append((None, doc, meta))
                        except Exception as e:
                            logger.warning(f"Error scoring document: {e}")
                            scored_results.append((None, doc, meta))

                    signal.alarm(0)  # Cancel alarm
                finally:
                    signal.signal(signal.SIGALRM, old_handler)

        except FuturesTimeoutError:
            logger.error(
                f"Rerank operation exceeded {timeout}s timeout, using fallback"
            )
            return results
        except Exception as e:
            logger.error(f"Rerank failed: {e}, using fallback")
            return results

        # Fallback if no scores were successful
        if successful_scores == 0:
            logger.info("No successful rerank scores, falling back to original ranking")
            return results

        # Filter by threshold
        threshold = float(Config.RERANK_THRESHOLD)
        filtered_results = [
            item
            for item in scored_results
            if item[0] is not None and item[0] >= threshold
        ]

        # If all results filtered out, return original
        if not filtered_results:
            logger.info(
                f"All results below threshold ({threshold}), returning original"
            )
            return results

        filtered_results.sort(key=lambda x: x[0], reverse=True)
        return [(doc, meta) for score, doc, meta in filtered_results]

    def query(
        self,
        text: str,
        n_results: int = SEARCH_N_RESULTS_DEFAULT,
        expand_graph: bool = SEARCH_EXPAND_GRAPH_DEFAULT,
        use_rerank: bool = SEARCH_USE_RERANK_DEFAULT,
    ) -> str:
        """
        Hybrid Semantic + Graph search.

        Args:
            text: Search query string
            n_results: Number of results to return (default: 3)
            expand_graph: Whether to include related notes via graph (default: True)
            use_rerank: Whether to apply reranking (default: True)

        Returns:
            Formatted context briefing with source documents and related notes
        """
        # 1. Semantic Search
        embedding = self.get_embedding(text)
        results = self.vector_collection.query(
            query_embeddings=[embedding], n_results=n_results
        )

        docs = results["documents"][0]
        metadatas = results["metadatas"][0]

        # 2. Rerank results if enabled
        if use_rerank and Config.ENABLE_RERANK and docs:
            reranked = self.rerank_results(text, list(zip(docs, metadatas)))
            if reranked:
                docs, metadatas = zip(*reranked)
                # Limit to n_results
                docs = docs[:n_results]
                metadatas = metadatas[:n_results]

        context_briefing = []
        seen_notes = set()

        for doc, meta in zip(docs, metadatas):
            note_identifier = meta.get("path") or meta["filename"]
            note_label = meta.get("path") or meta["filename"]
            context_briefing.append(f"--- Source: {note_label} ---\n{doc}")
            seen_notes.add(note_identifier)

            # 3. Graph Expansion
            if expand_graph:
                related = self.get_related_notes(note_identifier)
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
