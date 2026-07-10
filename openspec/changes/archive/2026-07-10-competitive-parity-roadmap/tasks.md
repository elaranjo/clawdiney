## 1. Eval harness

- [x] 1.1 Build fixture vault snapshot for evaluation, decoupled from the live vault
- [x] 1.2 Author golden-query fixture (`tests/eval/golden_queries.jsonl`) with expected note paths/chunk IDs
- [x] 1.3 Implement metrics module: recall@k, MRR, hit rate
- [x] 1.4 Implement `clawdiney-eval` CLI runner with baseline comparison and regression exit code
- [x] 1.5 Add mode flags to the harness: hybrid / BM25-only / vector-only, rerank on/off
- [x] 1.6 Record initial baseline scores against current `main` behavior
- [x] 1.7 Add harness run to `./scripts/run_tests.sh` or CI equivalent

## 2. Memory auto-write

- [x] 2.1 Decide and document vault location/frontmatter convention for agent-written memory (resolves design.md open question)
- [x] 2.2 Implement fact normalization step (parse natural-language fact into subject/predicate/value)
- [x] 2.3 Wire normalization into existing entity-resolution threshold for subject matching
- [x] 2.4 Implement dedupe-or-update logic against existing note sections/entities
- [x] 2.5 Implement minimum-confidence gate with rejection response
- [x] 2.6 Add `write_memory(fact, source, agent_id?)` MCP tool wired to `vault_writer`
- [x] 2.7 Add tests: explicit write, duplicate write, low-confidence rejection, no side effects on read-path tools
- [x] 2.8 Re-run eval harness to confirm no regression on read paths

## 3. Temporal facts

- [x] 3.1 Design schema migration: add `valid_at`, `invalidated_at` to `entities` and `relations`, bump schema_version
- [x] 3.2 Implement migration in `storage.py` with backfill (`valid_at` = migration time — no prior per-row timestamp existed to recover — `invalidated_at` NULL) and idempotency check
- [x] 3.3 Add migration test against a pre-migration fixture `brain.db`
- [x] 3.4 Update write paths to set `valid_at` on insert; supersede semantics (invalidate old row + insert new) implemented for the semantic/LLM relations layer (`replace_project_relations`), where facts genuinely change value. WikiLink/tag relations and `memory-auto-write`'s entity row stay on stamp-on-insert only — they're derived structure / stable identity, not asserted facts subject to value supersede (see storage.py docstrings)
- [x] 3.5 Add `as_of` optional parameter to `get_related_notes`, multi-hop traversal (`expand_neighborhood`, `find_paths`), and hybrid search graph expansion (`BrainQueryEngine.query`/`_build_context`)
- [x] 3.6 Default (no `as_of`) path filters to `invalidated_at IS NULL`, preserving current behavior
- [x] 3.7 Add tests: current-fact default query, historical `as_of` query, supersede-creates-new-row behavior
- [x] 3.8 Re-run eval harness to confirm parity with pre-migration baseline

## 4. Conflict resolution

- [x] 4.1 Add `is_conflict` column to `entities` and `relations` (default 0), additive migration (schema v4)
- [x] 4.2 Add `CONTRADICTS` relation type
- [x] 4.3 Implement conflict-detection at supersede time in the semantic-relations write path (section 3.4): same (source, rel_type) slot reasserted with a different target within one `replace_project_relations` call is a value change, not a removal — detected by cross-referencing newly-invalidated keys against newly-inserted rel_types (target-identity divergence stands in for a normalization-aware similarity threshold, since relation values here are entity references, not free text)
- [x] 4.4 Implement conflict-marking: both facts kept current (`invalidated_at` untouched) with `is_conflict=1`, plus a `CONTRADICTS` relation between the two conflicting target entities, instead of silent invalidation
- [x] 4.5 Add conflicts surfacing to `search_brain` and `explore_graph` MCP tool responses (text section, empty/omitted when none — tools return formatted strings, not structured JSON, consistent with the rest of the MCP surface)
- [x] 4.6 Implement explicit conflict-resolution operation (`BrainStorage.resolve_conflict`: mark one fact authoritative, invalidate the other, clear `is_conflict` on both)
- [x] 4.7 Add tests: conflicting update detected, non-conflicting refinement not flagged, conflict surfaced in query response, explicit resolution clears it
- [x] 4.8 Re-run eval harness to confirm no regression

## 5. Agent namespacing

- [x] 5.1 Add `agent_id TEXT NOT NULL DEFAULT 'default'` to `documents` and `entities`, additive migration (schema v5). `entities`' UNIQUE widened to `(vault, agent_id, name, kind)` (table rebuild, same technique as v2->v3) so same-named entities across agents don't collide; `documents` needed only a plain `ADD COLUMN` (its `(vault, path)` uniqueness is about physical files, not agents)
- [x] 5.2 Thread `agent_id` through `indexer.index_note` → `IncrementalIndexer.sync_file` → `VaultWriter.write_note`, defaulting to `"default"` at every layer so ordinary vault indexing is unaffected
- [x] 5.3 Add optional `agent_id` parameter to `search_brain`, `explore_graph`, `write_memory` (already had it from group 2, now actually scopes entity resolution + note path). **Scope adjustment**: `resolve_note`, `get_note_chunks`, `get_project_card` resolve notes by globbing the filesystem (`vault_root.rglob`), not by querying `documents`/`entities` — there is no agent_id to filter by in that code path, so adding the parameter there would be a no-op. Left unchanged rather than adding a misleading param
- [x] 5.4 Add explicit cross-namespace opt-in (`agent_id="*"` default, or a concrete agent id) to `how_do_projects_relate` via `storage.find_paths(..., agent_ids=...)`. Currently a no-op in practice — project/dependency entities aren't agent-scoped by this implementation (they come from the shared project-indexer pipeline) — but the parameter is wired through `find_paths`/`_load_edges` for when agent-scoped project data exists
- [x] 5.5 Add tests: default-namespace parity, cross-agent isolation, explicit cross-agent query — at the storage layer (`TestAgentNamespacing` in `test_storage.py`), the memory-write layer (`TestAgentNamespacing` in `test_memory_writer.py`), and the query-engine layer (`TestAgentScopedQuery` in `test_hybrid_search.py`)
- [x] 5.6 Re-run eval harness (no `agent_id` passed → unfiltered `"default"` path) to confirm parity with baseline

## 6. Configurable reranker

- [x] 6.1 Add `RERANK_MODEL` config value to `config.py` (default `BAAI/bge-reranker-v2-m3`)
- [x] 6.2 Update `reranker.py` to load model name from config instead of hardcoded constant (added `reset_reranker()` for test isolation of the process-wide singleton)
- [x] 6.3 Add test: default model unchanged when `RERANK_MODEL` unset, alternate model loads when set
- [x] 6.4 Run eval harness with at least one alternate cross-encoder model to document latency/precision trade-off (`cross-encoder/ms-marco-MiniLM-L-6-v2`: ~4s/query vs ~10s/query for the default on this CPU-fallback environment; identical recall/MRR/hit-rate on the small fixture — numbers only show latency delta, not precision on a harder vault)
- [x] 6.5 Document trade-offs (default, faster alternative, rerank-disabled) in config reference docs (README "Reranker configuration" + `.env.example`)

## 7. Positioning docs

- [x] 7.1 Collect final eval harness numbers across all modes (hybrid vs BM25-only vs vector-only, rerank on/off, model variants) — recorded in `BENCHMARKS.md`, with an explicit caveat that the small fixture scores every mode at 1.0 and doesn't yet demonstrate hybrid/rerank's marginal contribution (needs a harder golden set, tracked as an open item rather than glossed over)
- [x] 7.2 Add README section ("Why Embedded SQLite Instead of a Service Stack") contrasting footprint vs Neo4j+graph-DB+cache-style peer stacks, with an explicit trade-off caveat (single-writer, no horizontal scaling)
- [x] 7.3 Add eval harness results summary/table to a dedicated `BENCHMARKS.md` (retrieval-by-mode table + reranker model comparison + the embedded-vs-peers table), linked from README
- [x] 7.4 Update `CLAUDE.md` with new capabilities: retrieval eval harness, memory auto-write, bi-temporal fact tracking, conflict detection & resolution, agent namespacing, configurable reranker (new "Recent Improvements" subsections, plus Architecture/Project Structure/Key Files updates)
- [x] 7.5 Update MCP tool integration docs (README + CLAUDE.md) with new optional parameters: `agent_id` on `search_brain`/`explore_graph`/`how_do_projects_relate`, the "Unresolved conflicts" response section, and the new `write_memory` tool. `as_of` is documented as a `query_engine`/`storage` API parameter only — it is intentionally not exposed through any MCP tool in this implementation
