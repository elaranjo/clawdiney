# Design: sqlite-migration

## Context

Clawdiney indexes Obsidian vaults into ChromaDB (vectors, HTTP server), Neo4j (WikiLink/tag graph, Bolt), and Redis (exact-string query cache), all via docker-compose. Scale is small: ~6 projects, thousands of notes, tens of thousands of chunks — orders of magnitude below where server databases pay off. Search is vector-only (misses exact identifiers/acronyms) and reranking is done by prompting a generative Ollama model for a "score between 0 and 1" and parsing the float from free text (`query_engine.py:_score_single_doc` plus ~170 lines of ThreadPoolExecutor/timeout machinery around it).

Consumers: the MCP server tools (`search_brain`, `explore_graph`, etc.), CLI, watcher scripts. MCP tool signatures must not change.

## Goals / Non-Goals

**Goals:**
- Single-file embedded storage (`brain.db`): sqlite-vec (KNN) + FTS5 (BM25) + graph tables. Zero Docker.
- Hybrid retrieval with RRF fusion; cross-encoder reranking.
- All embedding calls behind `EmbeddingProvider`; `ollama.embed()` API.
- Delete Redis cache and dead code paths in `query_engine.py`.
- Tests for the storage layer run against real in-memory/tempfile SQLite (no mocks needed).

**Non-Goals:**
- Entity extraction via LLM, project cards, new MCP tools (`get_project_card`, `how_do_projects_relate`) — future change, but the graph schema is designed to accommodate it.
- Data migration from existing ChromaDB/Neo4j instances — the vault is the source of truth; a full re-index rebuilds everything.
- Changing chunking strategy, vault config, watcher, or MCP tool signatures.

## Decisions

### D1: sqlite-vec + FTS5 over LanceDB
Both are embedded and serverless. sqlite-vec wins because FTS5 (BM25) lives in the same database and same transaction as vectors and graph rows — one file, atomic per-note updates, one backup artifact. LanceDB would still need a separate FTS solution or its own experimental FTS, and a second storage location. At this scale (<100k vectors) sqlite-vec brute-force KNN is <100ms; no ANN index needed.

**Alternative rejected**: keep ChromaDB in embedded (PersistentClient) mode — still no BM25, still a separate store from the graph.

### D2: New `storage.py` module as the single DB gateway
One module owns the SQLite connection, schema creation/migration (PRAGMA `user_version`), and all SQL. Query engine, indexer, and vault writer call it; none of them holds SQL strings. This gives the tests one seam and keeps WAL/pragma setup (`journal_mode=WAL`, `foreign_keys=ON`) in one place. Connections are per-thread (`threading.local`) because the MCP server is multi-threaded and sqlite3 connections aren't thread-safe by default.

### D3: One database file, vault as a column
`brain.db` at a configurable path (`Config.BRAIN_DB_PATH`, default `~/.clawdiney/brain.db`); every row carries `vault` (documents) and graph entities carry `vault`. Simpler than per-vault files: the fallback-chain search (`_get_fallback_chain`) becomes a single SQL query with `vault IN (...)` ordered by chain position, instead of N collection lookups.

**Alternative rejected**: file per vault — complicates cross-vault fallback and multiplies connections.

### D4: Schema

```sql
PRAGMA user_version = 1;

CREATE TABLE documents (
    id INTEGER PRIMARY KEY,
    vault TEXT NOT NULL,
    path TEXT NOT NULL,              -- vault-relative
    content_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(vault, path)
);

CREATE TABLE chunks (
    id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    header TEXT,
    content TEXT NOT NULL,
    chunk_index INTEGER NOT NULL
);

CREATE VIRTUAL TABLE chunk_vectors USING vec0(
    chunk_id INTEGER PRIMARY KEY,
    embedding FLOAT[1024]            -- bge-m3 dimension; stored in meta table for validation
);

CREATE VIRTUAL TABLE chunk_fts USING fts5(
    content, header,
    content=chunks, content_rowid=id,
    tokenize='unicode61 remove_diacritics 2'
);

CREATE TABLE entities (
    id INTEGER PRIMARY KEY,
    vault TEXT NOT NULL,
    name TEXT NOT NULL,
    kind TEXT NOT NULL,              -- 'note' | 'tag' (future: 'project','service','pattern',...)
    path TEXT,                       -- for kind='note'
    description TEXT,
    UNIQUE(vault, name, kind)
);

CREATE TABLE relations (
    id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_id INTEGER NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    rel_type TEXT NOT NULL,          -- 'LINKS_TO' | 'HAS_TAG' (extensible)
    evidence_chunk_id INTEGER REFERENCES chunks(id) ON DELETE SET NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    UNIQUE(source_id, target_id, rel_type)
);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);  -- embedding_model, dimension
```

FTS5 uses external content (`content=chunks`) to avoid duplicating text; chunk insert/delete triggers keep it in sync. `meta` stores the embedding model+dimension; on startup, mismatch with config raises a clear "re-index required" error instead of garbage KNN results.

WikiLink targets that don't exist as notes yet get a `note` entity with `path=NULL` (dangling link), matching Obsidian semantics and current Neo4j behavior.

### D5: Hybrid search + RRF in SQL/Python
Two queries (FTS5 MATCH with `bm25()` ranking; vec0 KNN with `distance`), each fetching `n_results * 3` candidates, fused in Python: `score(chunk) = Σ 1/(60 + rank_i)`. Python fusion (vs. one giant SQL CTE) keeps it debuggable and lets one retriever fail soft. FTS5 query strings are sanitized (user text wrapped as quoted phrases OR-ed per token) so agent queries with `"`/`:`/`*` can't break MATCH syntax.

### D6: Cross-encoder reranker, lazy-loaded
`reranker.py` with `CrossEncoderReranker` wrapping `sentence_transformers.CrossEncoder("BAAI/bge-reranker-v2-m3")`. Lazy singleton: model loads on first rerank call, not import (~2GB RAM when active). `sentence-transformers` is an **optional extra** (`pip install clawdiney[rerank]`); if missing or load fails, log a warning once and return RRF order — behavior degrades, never breaks. Deletes `_score_single_doc`, `_score_documents_parallel`, `_process_futures`, `_filter_and_sort_results` and the `RERANK_MODEL_NAME` generative path.

**Alternative rejected**: rerank via Ollama's embedding of pairs — not what rerankers do; and Ollama has no cross-encoder scoring API today.

### D7: Graph queries as SQL
`get_related_notes`: two UNIONed SELECTs (bidirectional LINKS_TO join; shared-tag self-join through relations) with `DISTINCT`, scoped by vault. Multi-hop: `WITH RECURSIVE` CTE bounded by `depth <= 3` and a visited check (`MIN(distance)` grouping). networkx is **not** a dependency now — nothing in scope needs PageRank; add it later if entity ranking arrives.

### D8: Remove Redis outright
`query_cache.py` deleted, `ENABLE_QUERY_CACHE` config removed, `redis` dependency dropped. Local hybrid search on this scale is single-digit ms except embedding the query (~50-200ms via Ollama), which the cache never avoided for novel queries anyway — and agent queries are almost always novel.

### D9: Embedding provider wiring
`BrainQueryEngine`, indexers, and `vault_writer` receive/construct a provider via `get_embedding_provider(Config.EMBEDDING_PROVIDER)` (default `"ollama"`). Tenacity retry moves inside `OllamaEmbeddingProvider` so every caller inherits it. Provider migrated to `ollama.embed()` with native batch support.

## Risks / Trade-offs

- [sqlite-vec is pre-1.0] → API surface used is tiny (create vtable, INSERT, KNN SELECT); pin version in pyproject; storage.py isolates it so swapping to another embedded store touches one module.
- [Cross-encoder adds ~2GB RAM + first-call latency] → optional extra, lazy load, warm-up call at MCP startup in a background thread (same pattern as `_ensure_auto_sync`).
- [FTS5 MATCH syntax errors from raw agent queries] → sanitize/escape query text; unit tests with hostile inputs (`"`, `NEAR`, `*`, unbalanced parens).
- [Concurrent writes (watcher + MCP write tools)] → WAL mode + `busy_timeout=5000`; writes are per-note transactions, short-lived.
- [BREAKING for existing installs] → README migration note: `docker compose down`, `clawdiney-index`, done. Old services simply become unused.
- [bge-m3 dimension hardcoded in vec0 DDL] → dimension read from provider at schema-creation time and stored in `meta`; validated on open.

## Migration Plan

1. Land storage.py + new engine behind the same public interfaces; delete old backends in the same change (no dual-backend period — codebase is pre-1.0, single maintainer).
2. Bump version to 0.2.0; README: remove docker-compose from setup, add `clawdiney-index` re-index step.
3. Rollback = git revert + docker compose up (old data untouched in Docker volumes).

## Open Questions

- Rerank default: keep `SEARCH_USE_RERANK_DEFAULT` on, or off until model download UX is proven? (Proposed: on when extra installed, silently off otherwise.)
- `brain.db` default location: `~/.clawdiney/brain.db` vs. inside vault directory. Proposed: `~/.clawdiney/` (vault stays pure Markdown; Obsidian sync tools won't drag the DB).
