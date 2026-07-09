# hybrid-search

## Requirements

### Requirement: Embedded storage in a single SQLite file
The system SHALL store all indexed data (documents, chunks, vectors, full-text index, graph) in a single SQLite database file (`brain.db`) using the `sqlite-vec` extension for vectors and FTS5 for full-text search. The system MUST NOT require any external database server (ChromaDB, Neo4j, Redis) to index or search.

#### Scenario: Fresh install without Docker
- **WHEN** a user installs the package via pip with Ollama running and runs `clawdiney-index` without any Docker services
- **THEN** the vault is indexed into a local `brain.db` file and queries return results

#### Scenario: Database file location per vault
- **WHEN** multiple vaults are configured
- **THEN** each vault's data is isolated (per-vault tables or per-vault database) and queries scoped to one vault never return another vault's chunks unless fallback-chain expansion applies

### Requirement: Hybrid retrieval with RRF fusion
The query engine SHALL retrieve candidates from both BM25 (FTS5) and vector KNN (sqlite-vec) and fuse the two ranked lists using Reciprocal Rank Fusion with k=60 (`score = Σ 1/(60 + rank)`).

#### Scenario: Exact-term query favors BM25
- **WHEN** the query contains an exact identifier that appears verbatim in a note (e.g., a function name or acronym) but is semantically weak
- **THEN** the note ranks in the fused results even if vector similarity alone would miss it

#### Scenario: Semantic query favors vectors
- **WHEN** the query paraphrases note content with no shared keywords
- **THEN** the note ranks in the fused results via its vector similarity

#### Scenario: One retriever fails
- **WHEN** FTS5 returns no results (or errors) but vector search succeeds
- **THEN** the fused result equals the surviving retriever's ranking and no exception propagates to the caller

### Requirement: Cross-encoder reranking
The system SHALL rerank fused candidates with a cross-encoder model (`BAAI/bge-reranker-v2-m3` via `sentence-transformers`) scoring (query, chunk) pairs directly. The system MUST NOT use generative LLM prompting with textual score parsing for reranking.

#### Scenario: Rerank applied
- **WHEN** a query runs with reranking enabled and more candidates than `n_results` are fused
- **THEN** the final top-N ordering follows cross-encoder scores, descending

#### Scenario: Reranker unavailable
- **WHEN** the cross-encoder model cannot be loaded (missing dependency or model files)
- **THEN** the system logs a warning and returns the RRF-fused ranking unchanged

#### Scenario: Rerank disabled by config
- **WHEN** `ENABLE_RERANK` is false
- **THEN** no cross-encoder model is loaded and RRF ordering is returned

### Requirement: Result deduplication by note
Fused results SHALL be deduplicated by note path before final ranking, keeping the highest-ranked chunk per note, preserving current behavior.

#### Scenario: Multiple chunks from same note
- **WHEN** both retrievers return several chunks of the same note
- **THEN** only the highest-ranked chunk of that note appears in the final results

### Requirement: No query cache layer
The system SHALL NOT use an external query cache (Redis). Query latency targets MUST be met by the embedded storage directly.

#### Scenario: Redis absent
- **WHEN** the system starts and runs queries with no Redis server on the host
- **THEN** all queries succeed with no cache-related warnings or connection attempts

### Requirement: Incremental index consistency
Incremental sync SHALL update chunks, vectors, FTS entries, and graph rows atomically per file (single transaction), so a crash mid-sync never leaves a note half-indexed.

#### Scenario: Note modified
- **WHEN** a note's content hash changes and incremental sync runs
- **THEN** its old chunks/vectors/FTS rows are replaced by the new ones in one transaction

#### Scenario: Note deleted
- **WHEN** a note is removed from the vault and incremental sync runs
- **THEN** all its chunks, vectors, FTS entries, and graph relations are removed
