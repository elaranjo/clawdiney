import logging
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from concurrent.futures import TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, TypedDict

import chromadb
import httpx
import ollama
from neo4j import GraphDatabase
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from .chunking import Chunk, markdown_chunking
from .config import Config
from .constants import (
    RERANK_BATCH_SIZE,
    RERANK_TIMEOUT_SECONDS,
    SEARCH_EXPAND_GRAPH_DEFAULT,
    SEARCH_N_RESULTS_DEFAULT,
    SEARCH_USE_RERANK_DEFAULT,
)
from .logging_config import setup_logging
from .query_cache import QueryCache
from .rag_optimizer import MMRReranker, QueryPreprocessor
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


class BrainQueryEngine:
    def __init__(self, vault: str | None = None):
        self.current_vault = vault or Config.get_default_vault()

        vault_path = Config.get_vault_path(self.current_vault)
        if isinstance(vault_path, (str, Path)):
            self.vault_root = Path(vault_path).expanduser().resolve()
        else:
            self.vault_root = Path(Config.VAULT_PATH).expanduser().resolve()

        self.vault_config: VaultConfig | None = None
        try:
            if self.vault_root.joinpath("clawdiney.toml").exists():
                self.vault_config = load_vault_config(self.vault_root)
        except Exception:
            pass

        # ChromaDB Setup - Always use HTTP client
        chroma_config = Config.get_chroma_client_config()
        self.chroma_client = chromadb.HttpClient(
            host=chroma_config["host"], port=chroma_config["port"]
        )
        # Configura timeout para 300 segundos no cliente httpx subjacente
        self.chroma_client.timeout = httpx.Timeout(300.0)

        collection_name = f"vault_{self.current_vault}"
        try:
            self.vector_collection = self.chroma_client.get_collection(
                name=collection_name
            )
        except Exception:
            self.vector_collection = self.chroma_client.get_collection(
                name="obsidian_vault"
            )

        # Internal collection cache for fallback lookups
        self._collection_cache: dict[str, Any] = {}

        # Neo4j Setup
        self.neo4j_driver = GraphDatabase.driver(
            Config.NEO4J_URI,
            auth=(Config.NEO4J_USER, Config.get_neo4j_password()),
        )

        # Query Cache Setup (Redis)
        self.cache = QueryCache() if Config.ENABLE_QUERY_CACHE else None

        # RAG Optimizers
        self.query_preprocessor = QueryPreprocessor(
            expand_abbreviations=True, remove_stop_words=False
        )
        self.mmr_reranker = MMRReranker(lambda_param=0.7)

    def close(self) -> None:
        """Close all database connections (Neo4j + ChromaDB + Redis)."""
        self.neo4j_driver.close()
        if hasattr(self.chroma_client, "close"):
            self.chroma_client.close()
        if self.cache:
            self.cache.close()

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

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ConnectionError, TimeoutError, RuntimeError)),
        reraise=True,
    )
    def get_embedding(self, text: str) -> list[float]:
        """Get embedding with exponential backoff retry."""
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
            raise ValueError(
                f"Path '{path}' is outside the vault"
            ) from exc

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

    def get_related_notes(self, note_ref: str, vault: str | None = None) -> list[str]:
        """
        Fetches notes that are linked to the given note in Neo4j, including tag-based relationships.

        Uses the optimized schema:
        - (:Note)-[:LINKS_TO]->(:Note) for wikilinks
        - (:Note)-[:HAS_TAG]->(:Tag) for tags (avoids O(n²) cartesian join)
        """
        vault_name = vault or self.current_vault
        with self.neo4j_driver.session() as session:
            query = """
            MATCH (n:Note {vault: $vault})-[:LINKS_TO]-(related:Note {vault: $vault})
            WHERE n.path = $note_ref OR n.name = $note_ref
            WITH collect(related) AS linked_notes

            MATCH (n:Note {vault: $vault})-[:HAS_TAG]->(t:Tag)<-[:HAS_TAG]-(related:Note {vault: $vault})
            WHERE n.path = $note_ref OR n.name = $note_ref
            WITH linked_notes, collect(DISTINCT related) AS tag_related

            // Combine and deduplicate
            WITH linked_notes + tag_related AS all_related
            UNWIND all_related AS related
            RETURN DISTINCT related.name AS name, related.path AS path
            """
            result = session.run(query, note_ref=note_ref, vault=vault_name)
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

        # Score documents in parallel
        scored_results, successful_scores = self._score_documents_parallel(
            query, results, timeout, batch_size
        )

        # Fallback if no scores were successful
        if successful_scores == 0:
            logger.info("No successful rerank scores, falling back to original ranking")
            return results

        # Filter and sort results
        return self._filter_and_sort_results(scored_results, results)

    def _score_documents_parallel(
        self,
        query: str,
        results: list[tuple[str, dict[str, Any]]],
        timeout: int,
        batch_size: int,
    ) -> tuple[list[tuple[float | None, str, dict[str, Any]]], int]:
        """
        Score documents in parallel using ThreadPoolExecutor.

        Args:
            query: Search query string
            results: List of (document, metadata) tuples
            timeout: Maximum seconds for entire operation
            batch_size: Number of concurrent workers

        Returns:
            Tuple of (scored_results, successful_scores_count)
        """
        scored_results: list[tuple[float | None, str, dict[str, Any]]] = []
        successful_scores = [0]  # Use list for mutability

        try:
            with ThreadPoolExecutor(max_workers=batch_size) as executor:
                futures = {
                    executor.submit(self._score_single_doc, query, doc): (doc, meta)
                    for doc, meta in results
                }

                self._process_futures(
                    futures, timeout, scored_results, successful_scores
                )

        except Exception as e:
            logger.error(f"Rerank failed: {e}, using fallback")
            return [], 0

        return scored_results, successful_scores[0]

    def _process_futures(
        self,
        futures: dict,
        timeout: int,
        scored_results: list[tuple[float | None, str, dict[str, Any]]],
        successful_scores: list[int],
    ) -> None:
        """
        Process futures with timeout handling.

        Args:
            futures: Dict mapping futures to (doc, meta) tuples
            timeout: Maximum seconds to wait
            scored_results: List to append results to (modified in place)
            successful_scores: List with single int counter (modified in place)
        """
        pending_futures = set(futures.keys())

        while pending_futures:
            completed, pending_futures = wait(
                pending_futures, timeout=timeout, return_when=FIRST_COMPLETED
            )

            if not completed and pending_futures:
                logger.warning("Rerank timeout reached, some documents not scored")
                for future in pending_futures:
                    doc, meta = futures[future]
                    scored_results.append((None, doc, meta))
                break

            for future in completed:
                doc, meta = futures[future]
                try:
                    score = future.result(timeout=0)
                    if score is not None:
                        successful_scores[0] += 1
                    scored_results.append((score, doc, meta))
                except FuturesTimeoutError:
                    logger.warning("Document scoring timed out")
                    scored_results.append((None, doc, meta))
                except Exception as e:
                    logger.warning(f"Error scoring document: {e}")
                    scored_results.append((None, doc, meta))

    def _filter_and_sort_results(
        self,
        scored_results: list[tuple[float | None, str, dict[str, Any]]],
        original_results: list[tuple[str, dict[str, Any]]],
    ) -> list[tuple[str, dict[str, Any]]]:
        """
        Filter scored results by threshold and sort by score.

        Args:
            scored_results: List of (score, doc, meta) tuples
            original_results: Original results for fallback

        Returns:
            Filtered and sorted list of (doc, meta) tuples
        """
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
            return original_results

        filtered_results.sort(key=lambda x: x[0], reverse=True)
        return [(doc, meta) for score, doc, meta in filtered_results]

    def _deduplicate_results(
        self, docs: list[str], metadatas: list[dict[str, Any]]
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """
        Remove duplicate results based on note path/filename.

        When ChromaDB returns multiple chunks from the same note,
        keep only the first (highest ranked) occurrence.

        Args:
            docs: List of document contents
            metadatas: List of metadata dicts

        Returns:
            Tuple of (deduplicated_docs, deduplicated_metadatas)
        """
        seen_paths = set()
        unique_docs = []
        unique_metadatas = []

        for doc, meta in zip(docs, metadatas):
            note_path = meta.get("path") or meta["filename"]
            if note_path not in seen_paths:
                seen_paths.add(note_path)
                unique_docs.append(doc)
                unique_metadatas.append(meta)

        return unique_docs, unique_metadatas

    def _diversify_results(
        self, docs: list[str], metadatas: list[dict[str, Any]], k: int
    ) -> tuple[list[str], list[dict[str, Any]]]:
        """
        Diversify results using a simple heuristic when MMR embeddings unavailable.

        Selects results from different notes when possible, avoiding multiple
        chunks from the same source.

        Args:
            docs: List of document contents
            metadatas: List of metadata dicts
            k: Number of results to return

        Returns:
            Tuple of (diversified_docs, diversified_metadatas)
        """
        # Group by note path
        by_note: dict[str, list[tuple[str, dict[str, Any]]]] = {}
        for doc, meta in zip(docs, metadatas):
            note_path = meta.get("path") or meta["filename"]
            if note_path not in by_note:
                by_note[note_path] = []
            by_note[note_path].append((doc, meta))

        # Take one chunk per note until we have k results
        diversified: list[tuple[str, dict[str, Any]]] = []
        for note_path, chunks in by_note.items():
            if len(diversified) >= k:
                break
            diversified.append(chunks[0])  # Take first (highest ranked) chunk

        if not diversified:
            return [], []

        docs_result, metas_result = zip(*diversified)
        return list(docs_result), list(metas_result)

    def _get_fallback_chain(self) -> list[str]:
        chain: list[str] = [self.current_vault]
        if self.vault_config:
            for lv in self.vault_config.linked_vaults:
                if lv not in chain:
                    chain.append(lv)
        if "general" not in chain:
            chain.append("general")
        return chain

    def _get_vault_collection(self, vault_name: str) -> Any:
        if vault_name in self._collection_cache:
            return self._collection_cache[vault_name]
        try:
            collection = self.chroma_client.get_collection(f"vault_{vault_name}")
            self._collection_cache[vault_name] = collection
            return collection
        except Exception:
            return None

    def _search_vectors_in_collection(
        self, query: str, collection: Any, n_results: int
    ) -> tuple[list[str], list[dict[str, Any]], str]:
        embedding = self.get_embedding(query)
        results = collection.query(
            query_embeddings=[embedding], n_results=n_results
        )
        docs = results["documents"][0]
        metadatas = results["metadatas"][0]
        return docs, metadatas, ""

    def query(
        self,
        text: str,
        n_results: int = SEARCH_N_RESULTS_DEFAULT,
        expand_graph: bool = SEARCH_EXPAND_GRAPH_DEFAULT,
        use_rerank: bool = SEARCH_USE_RERANK_DEFAULT,
        use_mmr: bool = False,
        vault_override: str | None = None,
    ) -> str:
        vault_name = vault_override or self.current_vault

        if self.cache:
            cache_key = f"{vault_name}:{text}"
            cached = self.cache.get(cache_key)
            if cached:
                logger.info(f"Cache hit for query: {text[:50]}...")
                return cached["formatted_results"]

        processed_query = self.query_preprocessor.preprocess(text)
        if processed_query != text and logger.isEnabledFor(logging.DEBUG):
            logger.debug("Query preprocessed: '%s' -> '%s'", text, processed_query)

        fallback_chain = self._get_fallback_chain()
        if vault_override and vault_override not in fallback_chain:
            fallback_chain = [vault_override] + [v for v in fallback_chain if v != vault_override]

        all_docs: list[str] = []
        all_metas: list[dict[str, Any]] = []
        seen_paths: set[str] = set()
        searched_vaults: set[str] = set()

        fetch_n = n_results * 3 if use_mmr else n_results

        for vname in fallback_chain:
            if len(all_docs) >= n_results:
                break
            if vname in searched_vaults:
                continue
            searched_vaults.add(vname)

            collection = self._get_vault_collection(vname)
            if collection is None:
                logger.debug("Collection not found for vault '%s', skipping", vname)
                continue

            remaining = n_results - len(all_docs)
            try:
                docs, metadatas, _ = self._search_vectors_in_collection(
                    processed_query, collection, remaining + 5
                )
            except Exception as e:
                logger.warning("Search failed for vault '%s': %s", vname, e)
                continue

            for doc, meta in zip(docs, metadatas):
                note_path = meta.get("path") or meta.get("filename", "")
                if note_path not in seen_paths:
                    meta = dict(meta)
                    meta["vault_source"] = vname
                    seen_paths.add(note_path)
                    all_docs.append(doc)
                    all_metas.append(meta)
                    if len(all_docs) >= n_results:
                        break

        docs, metadatas = all_docs[:n_results], all_metas[:n_results]

        if use_mmr:
            docs, metadatas = self._diversify_results(docs, metadatas, n_results)
        if use_rerank and Config.ENABLE_RERANK:
            reranked = self.rerank_results(processed_query, list(zip(docs, metadatas)))
            if reranked:
                docs, metadatas = zip(*reranked)
                docs = list(docs[:n_results])
                metadatas = list(metadatas[:n_results])

        result = self._build_context_multi_vault(docs, metadatas, expand_graph)

        if self.cache:
            cache_key = f"{vault_name}:{text}"
            self.cache.set(cache_key, {"formatted_results": result})

        return result

    def _build_context_multi_vault(
        self,
        docs: list[str],
        metadatas: list[dict[str, Any]],
        expand_graph: bool,
    ) -> str:
        context_briefing = []
        seen_notes = set()

        for doc, meta in zip(docs, metadatas):
            note_label = meta.get("path") or meta["filename"]
            vault_source = meta.get("vault_source", "?")
            context_briefing.append(f"--- Source [{vault_source}]: {note_label} ---\n{doc}")
            seen_notes.add(note_label)

            if expand_graph:
                related = self.get_related_notes(note_label)
                for rel_note in related:
                    if rel_note not in seen_notes:
                        context_briefing.append(
                            f"--- Related Note: {rel_note} (Linked via {note_label}) ---"
                        )
                        seen_notes.add(rel_note)

        return "\n\n".join(context_briefing)

    def _search_vectors(
        self, query: str, n_results: int
    ) -> tuple[list[str], list[dict[str, Any]]]:
        embedding = self.get_embedding(query)
        results = self.vector_collection.query(
            query_embeddings=[embedding], n_results=n_results
        )
        return results["documents"][0], results["metadatas"][0]

    def _apply_reranking(
        self,
        docs: list[str],
        metadatas: list[dict[str, Any]],
        query: str,
        n_results: int,
        use_mmr: bool,
        use_rerank: bool,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        if not docs:
            return docs, metadatas

        if use_mmr:
            logger.info("Applying diversity reranking...")
            docs, metadatas = self._diversify_results(docs, metadatas, n_results)

        if use_rerank and Config.ENABLE_RERANK:
            reranked = self.rerank_results(query, list(zip(docs, metadatas)))
            if reranked:
                docs, metadatas = zip(*reranked)
                docs = list(docs[:n_results])
                metadatas = list(metadatas[:n_results])

        return docs, metadatas

    def _build_context(
        self,
        docs: list[str],
        metadatas: list[dict[str, Any]],
        expand_graph: bool,
    ) -> str:
        context_briefing = []
        seen_notes = set()

        for doc, meta in zip(docs, metadatas):
            note_label = meta.get("path") or meta["filename"]
            context_briefing.append(f"--- Source: {note_label} ---\n{doc}")
            seen_notes.add(note_label)

            if expand_graph:
                related = self.get_related_notes(note_label)
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
