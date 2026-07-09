# Proposal: sqlite-migration

## Why

Clawdiney currently requires three Docker services (Neo4j, ChromaDB, Redis) to index and search a personal Obsidian vault — an infrastructure footprint that is the project's single biggest adoption barrier and is disproportionate to the data scale (thousands of notes, tens of thousands of chunks). Additionally, search quality is limited by vector-only retrieval (no BM25 for exact terms, acronyms, proper nouns) and a fragile LLM-generative reranker that parses floats from free-text output.

## What Changes

- **BREAKING**: Replace ChromaDB (HTTP server) with `sqlite-vec` + FTS5 embedded in a single local `brain.db` file. Requires full re-index; ChromaDB collections are abandoned.
- **BREAKING**: Replace Neo4j with graph tables (`entities`, `relations`) in the same SQLite file. WikiLinks (`LINKS_TO`) and tags (`HAS_TAG`) ported as typed relations. Cypher queries replaced by SQL joins/recursive CTEs.
- **BREAKING**: Remove Redis query cache entirely. Exact-string query caching has near-zero hit rate with agent-generated queries; local SQLite search is fast enough without it.
- Add hybrid search: BM25 (FTS5) + vector KNN (sqlite-vec) fused via Reciprocal Rank Fusion (RRF).
- Replace LLM-generative rerank (`ollama.generate` + float parsing, ~170 lines of timeout/parallel machinery) with a real cross-encoder (`BAAI/bge-reranker-v2-m3` via `sentence-transformers`).
- Route all embedding calls through the existing-but-unused `embedding_providers.py` abstraction; migrate from deprecated `ollama.embeddings()` to `ollama.embed()`.
- Remove duplicated/dead code paths in `query_engine.py` (`_build_context` vs `_build_context_multi_vault`, `_search_vectors` vs `_search_vectors_in_collection`, `_deduplicate_results`, `_apply_reranking`).
- Remove `docker/docker-compose.yml` requirement from setup; installation becomes `pip install` + Ollama.

## Capabilities

### New Capabilities
- `hybrid-search`: BM25 + vector retrieval with RRF fusion and cross-encoder reranking over an embedded SQLite store (sqlite-vec + FTS5).
- `graph-store`: Typed entity/relation graph in SQLite replacing Neo4j — WikiLink and tag relationships, 1-2 hop neighborhood queries with evidence traceability.
- `embedding-abstraction`: All embedding generation flows through the `EmbeddingProvider` protocol with pluggable backends (Ollama default, OpenAI optional), using the current `ollama.embed` API.

### Modified Capabilities
<!-- No existing specs in openspec/specs/ — all behavior is captured as new capabilities above. -->

## Impact

- **Code**: `query_engine.py` (major rewrite of storage/search layers), `indexer.py`, `incremental_indexer.py`, `vault_writer.py`, `mcp_server.py` (health_check), `config.py`, `query_cache.py` (deleted), `embedding_providers.py` (now actually used).
- **Dependencies**: remove `chromadb`, `neo4j`, `redis`; add `sqlite-vec`, `sentence-transformers`.
- **Infrastructure**: `docker/docker-compose.yml` no longer required (removed from setup path); data lives in a single `brain.db` per install.
- **MCP API surface**: tool signatures unchanged (`search_brain`, `explore_graph`, `resolve_note`, `get_note_chunks`, write tools); `health_check` output changes (checks SQLite + Ollama instead of ChromaDB/Neo4j/Redis).
- **Tests**: storage-layer tests rewritten against SQLite (can run fully offline without mocks for the DB layer); Redis/Neo4j/ChromaDB mocks deleted.
- **Migration**: one-time full re-index required (`clawdiney-index`); no data migration tool needed since the vault itself is the source of truth.
