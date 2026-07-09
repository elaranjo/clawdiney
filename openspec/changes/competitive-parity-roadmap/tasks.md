## 1. Eval harness

- [x] 1.1 Build fixture vault snapshot for evaluation, decoupled from the live vault
- [x] 1.2 Author golden-query fixture (`tests/eval/golden_queries.jsonl`) with expected note paths/chunk IDs
- [x] 1.3 Implement metrics module: recall@k, MRR, hit rate
- [x] 1.4 Implement `clawdiney-eval` CLI runner with baseline comparison and regression exit code
- [x] 1.5 Add mode flags to the harness: hybrid / BM25-only / vector-only, rerank on/off
- [x] 1.6 Record initial baseline scores against current `main` behavior
- [x] 1.7 Add harness run to `./scripts/run_tests.sh` or CI equivalent

## 2. Memory auto-write

- [ ] 2.1 Decide and document vault location/frontmatter convention for agent-written memory (resolves design.md open question)
- [ ] 2.2 Implement fact normalization step (parse natural-language fact into subject/predicate/value)
- [ ] 2.3 Wire normalization into existing entity-resolution threshold for subject matching
- [ ] 2.4 Implement dedupe-or-update logic against existing note sections/entities
- [ ] 2.5 Implement minimum-confidence gate with rejection response
- [ ] 2.6 Add `write_memory(fact, source, agent_id?)` MCP tool wired to `vault_writer`
- [ ] 2.7 Add tests: explicit write, duplicate write, low-confidence rejection, no side effects on read-path tools
- [ ] 2.8 Re-run eval harness to confirm no regression on read paths

## 3. Temporal facts

- [ ] 3.1 Design schema migration: add `valid_at`, `invalidated_at` to `entities` and `relations`, bump schema_version
- [ ] 3.2 Implement migration in `storage.py` with backfill (`valid_at` = existing row creation time, `invalidated_at` NULL) and idempotency check
- [ ] 3.3 Add migration test against a pre-migration fixture `brain.db`
- [ ] 3.4 Update write paths (indexer, incremental_indexer, memory-auto-write) to set `valid_at` on insert and `invalidated_at` on supersede instead of overwriting rows
- [ ] 3.5 Add `as_of` optional parameter to `get_related_notes`, multi-hop traversal, and hybrid search graph joins
- [ ] 3.6 Default (no `as_of`) path filters to `invalidated_at IS NULL`, preserving current behavior
- [ ] 3.7 Add tests: current-fact default query, historical `as_of` query, supersede-creates-new-row behavior
- [ ] 3.8 Re-run eval harness to confirm parity with pre-migration baseline

## 4. Conflict resolution

- [ ] 4.1 Add `is_conflict` column to `entities` and `relations` (default 0), additive migration
- [ ] 4.2 Add `CONTRADICTS` relation type
- [ ] 4.3 Implement conflict-detection comparison (normalization-aware similarity threshold) at supersede time in write paths from section 3.4
- [ ] 4.4 Implement conflict-marking: write both facts with `is_conflict=1` and a `CONTRADICTS` relation instead of silent invalidation
- [ ] 4.5 Add `conflicts` field to `search_brain` and `explore_graph` MCP tool responses (empty list when none)
- [ ] 4.6 Implement explicit conflict-resolution operation (mark one fact authoritative, invalidate the other, clear `is_conflict`)
- [ ] 4.7 Add tests: conflicting update detected, non-conflicting refinement not flagged, conflict surfaced in query response, explicit resolution clears it
- [ ] 4.8 Re-run eval harness to confirm no regression

## 5. Agent namespacing

- [ ] 5.1 Add `agent_id TEXT NOT NULL DEFAULT 'default'` to `documents`, `entities`, and write-path tables, additive migration
- [ ] 5.2 Update indexer/incremental_indexer to stamp `agent_id="default"` on vault-derived rows
- [ ] 5.3 Add optional `agent_id` parameter (default `"default"`) to `search_brain`, `explore_graph`, `resolve_note`, `get_note_chunks`, `get_project_card`, `write_memory`
- [ ] 5.4 Add explicit cross-namespace opt-in (`agent_id="*"` or list) to `how_do_projects_relate`
- [ ] 5.5 Add tests: default-namespace parity with pre-change behavior, cross-agent isolation, explicit cross-agent query
- [ ] 5.6 Re-run eval harness scoped to `"default"` agent to confirm parity

## 6. Configurable reranker

- [ ] 6.1 Add `RERANK_MODEL` config value to `config.py` (default `BAAI/bge-reranker-v2-m3`)
- [ ] 6.2 Update `reranker.py` to load model name from config instead of hardcoded constant
- [ ] 6.3 Add test: default model unchanged when `RERANK_MODEL` unset, alternate model loads when set
- [ ] 6.4 Run eval harness with at least one alternate cross-encoder model to document latency/precision trade-off
- [ ] 6.5 Document trade-offs (default, faster alternative, rerank-disabled) in config reference docs

## 7. Positioning docs

- [ ] 7.1 Collect final eval harness numbers across all modes (hybrid vs BM25-only vs vector-only, rerank on/off, model variants)
- [ ] 7.2 Rewrite README section contrasting embedded-SQLite footprint vs Neo4j+Chroma+Redis-style peer stacks
- [ ] 7.3 Add eval harness results summary/table to README or a dedicated `BENCHMARKS.md`
- [ ] 7.4 Update `CLAUDE.md` with new capabilities (write_memory, temporal facts, conflict resolution, agent namespacing, configurable reranker, eval harness)
- [ ] 7.5 Update MCP tool integration docs with new optional parameters (`agent_id`, `as_of`, `conflicts` field, `write_memory`)
