# Tasks: sqlite-migration

## 1. Foundation: storage module + dependencies

- [x] 1.1 Update `pyproject.toml`: remove `chromadb`, `neo4j`, `redis`; add `sqlite-vec` (pinned); add optional extra `rerank = ["sentence-transformers>=2.7"]`; bump version to 0.2.0
- [x] 1.2 Create `src/clawdiney/storage.py`: connection management (per-thread via `threading.local`), pragmas (WAL, foreign_keys, busy_timeout=5000), sqlite-vec extension loading, schema creation with `PRAGMA user_version`, `meta` table (embedding model + dimension validation on open)
- [x] 1.3 Implement schema DDL in storage.py: `documents`, `chunks`, `chunk_vectors` (vec0), `chunk_fts` (FTS5 external-content + sync triggers), `entities`, `relations`, `meta` (per design.md D4)
- [x] 1.4 Add `Config.BRAIN_DB_PATH` (default `~/.clawdiney/brain.db`) and `Config.EMBEDDING_PROVIDER` (default `ollama`); remove `ENABLE_QUERY_CACHE`, Redis, ChromaDB, and Neo4j config entries
- [x] 1.5 Unit tests for storage.py: schema creation, per-thread connections, dimension mismatch raises "re-index required", FTS triggers keep chunk_fts in sync on insert/update/delete (real tempfile SQLite, no mocks)

## 2. Embedding provider wiring

- [x] 2.1 Migrate `OllamaEmbeddingProvider` to `ollama.embed()` API with native batch support in `embed_batch`; move tenacity retry (3 attempts, exponential backoff) inside the provider
- [x] 2.2 Wire `get_embedding_provider(Config.EMBEDDING_PROVIDER)` into `BrainQueryEngine`, `indexer.py`, `incremental_indexer.py`, `vault_writer.py`; delete all direct `ollama.embeddings()` calls
- [x] 2.3 Update/add tests: provider embed/embed_batch response-shape handling (mock ollama client), retry on transient ConnectionError, engine uses provider seam

## 3. Storage write path: indexer migration

- [x] 3.1 Rewrite `indexer.py` to write documents/chunks/vectors/FTS/graph rows into storage.py in one transaction per note; extract WikiLinks → `LINKS_TO` relations and tags → `HAS_TAG` relations (dangling link targets get `path=NULL` note entities, confidence=1.0)
- [x] 3.2 Rewrite `incremental_indexer.py` against storage.py: hash-diff unchanged, per-file atomic replace (delete old chunks/vectors/FTS/relations, insert new), deletion removes all note rows
- [x] 3.3 Update `vault_writer.py` reindex hooks to call the new storage-backed indexing functions
- [x] 3.4 Tests: index sample vault fixture into tempfile DB, assert chunks/vectors/FTS/relations rows; re-index idempotency (no duplicate relations); note modify/delete scenarios from hybrid-search spec

## 4. Graph queries (replaces Neo4j)

- [x] 4.1 Implement in storage.py: `get_related_notes(note_ref, vault)` — bidirectional LINKS_TO ∪ shared-tag SQL, DISTINCT, vault-scoped; unknown note returns empty list
- [x] 4.2 Implement `expand_neighborhood(entity, vault, depth<=3)` recursive CTE with cycle safety (min distance, visited once), returning (entity, rel_type, distance)
- [x] 4.3 Port `query_engine.get_related_notes` and `mcp_server.explore_graph` to the SQL implementations; delete Neo4j driver setup/teardown
- [x] 4.4 Tests: WikiLink neighbors (both directions), tag neighbors, cross-vault isolation, 2-hop expansion, cycle graph termination

## 5. Hybrid search read path

- [x] 5.1 Implement in storage.py: `search_bm25(query, vaults, k)` with FTS5 query sanitization (tokenize user text, quoted-phrase OR), and `search_vectors(embedding, vaults, k)` KNN
- [x] 5.2 Implement RRF fusion (k=60) in `query_engine.py`: fetch `n_results*3` from each retriever, fuse, dedupe by note path keeping best chunk, fail-soft when one retriever errors/empty
- [x] 5.3 Rewrite `BrainQueryEngine.__init__`/`close`/`query` on storage.py: fallback chain becomes vault-ordered SQL filter; delete ChromaDB client, collection cache, `_search_vectors_in_collection`
- [x] 5.4 Tests: exact-term query found via BM25, paraphrase found via vectors, RRF ordering, one-retriever-failure fail-soft, dedup by note, hostile FTS inputs (`"`, `*`, `NEAR`, unbalanced parens)

## 6. Cross-encoder reranker

- [x] 6.1 Create `src/clawdiney/reranker.py`: `CrossEncoderReranker` with lazy singleton load of `BAAI/bge-reranker-v2-m3`; import/load failure → warn once, return input order unchanged
- [x] 6.2 Replace generative rerank in `query_engine.py`: delete `_score_single_doc`, `_score_documents_parallel`, `_process_futures`, `_filter_and_sort_results`, `rerank_results` machinery; wire reranker after RRF, honoring `ENABLE_RERANK`
- [x] 6.3 Remove `RERANK_MODEL_NAME`, `RERANK_TIMEOUT_SECONDS`, `RERANK_BATCH_SIZE`, `RERANK_THRESHOLD` generative-path config/constants (keep `ENABLE_RERANK`)
- [x] 6.4 Tests: rerank ordering follows mocked cross-encoder scores, disabled via config loads no model, missing dependency falls back to RRF order with warning

## 7. Dead code and Redis removal

- [x] 7.1 Delete `query_cache.py` and its tests; remove cache get/set from `query_engine.query`
- [x] 7.2 Delete dead/duplicated paths in `query_engine.py`: `_build_context` (keep multi-vault variant), `_search_vectors` (old), `_deduplicate_results`, `_apply_reranking`; replace `except Exception: pass` on vault-config load with logged warning
- [x] 7.3 Grep-verify no remaining imports/references to `chromadb`, `neo4j`, `redis`, `query_cache` anywhere in `src/` and `tests/`

## 8. MCP server, CLI, scripts

- [x] 8.1 Rewrite `mcp_server.health_check`: check brain.db (open + counts), Ollama, reranker availability; per-vault status from `documents` table
- [x] 8.2 Update `cli.py` and `scripts/` (sync_vault, watch_vault, index_projects, watch_projects) for storage-backed indexing; remove service-connection preflight checks for Chroma/Neo4j/Redis
- [x] 8.3 Optional reranker warm-up thread at MCP startup (same pattern as `_ensure_auto_sync`)
- [x] 8.4 Update MCP integration tests (`test_mcp_*`): replace Chroma/Neo4j/Redis mocks with tempfile brain.db fixtures

## 9. Docs, cleanup, release

- [x] 9.1 Update `CLAUDE.md` and `README.md`: remove docker-compose from setup, document `pip install clawdiney[rerank]`, `BRAIN_DB_PATH`, and one-time `clawdiney-index` migration step for existing users
- [x] 9.2 Move `docker/docker-compose.yml` to optional/legacy status (or delete) and update `scripts/setup_brain.sh`
- [x] 9.3 Full suite green: `./venv/bin/python3 -m pytest tests/ -v`; `ruff check` and `mypy` clean
- [x] 9.4 End-to-end smoke test: fresh `brain.db`, `clawdiney-index` on real vault, `search_brain` via query_engine CLI returns sane results with and without rerank extra installed
