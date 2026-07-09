## Context

Clawdiney's current architecture (embedded SQLite, hybrid BM25+vector search, RRF fusion, optional cross-encoder rerank, deterministic + LLM graph extraction) is read-heavy: it indexes an Obsidian vault and serves retrieval to MCP clients. It has no write path back from agent conversations, no notion of time (facts are point-in-time, overwritten on re-index), no multi-agent isolation, and no evaluation harness to prove retrieval quality. Peers (mem0, Zep/Graphiti, Letta) differentiate on exactly these axes. This design covers seven capabilities, sequenced so each later one can rely on the guarantees of the earlier ones, implemented as a single coordinated change but landed incrementally.

**Stakeholders**: single maintainer (elaranjo), used as a personal/team knowledge substrate for AI coding agents via MCP.

**Constraints**: no new required infra (must stay embedded-SQLite-only); existing `brain.db` files must migrate without data loss; MCP tool surface (`search_brain`, `explore_graph`, `resolve_note`, `get_note_chunks`, `get_project_card`, `how_do_projects_relate`) must remain backward compatible in signature (new params optional).

## Goals / Non-Goals

**Goals:**
- Establish objective retrieval-quality measurement before changing retrieval behavior.
- Add a write path so the system can accumulate memory from agent interactions, not just vault edits.
- Model fact validity over time and surface contradictions instead of silently clobbering data.
- Support multiple agents/projects sharing one `brain.db` without cross-contamination.
- Make the rerank stage swappable/skippable with a documented cost/quality trade-off.
- Make the embedded-storage advantage a visible, benchmarked selling point.

**Non-Goals:**
- Not building a hosted/multi-tenant SaaS — `agent-namespacing` isolates logical namespaces in one local file, not network-level multi-tenancy.
- Not replacing the deterministic + LLM entity-extraction pipeline — `conflict-resolution` and `temporal-facts` extend it, not rewrite it.
- Not adding a vector DB or graph DB dependency — everything stays inside `brain.db`.
- Not building a UI for reviewing conflicts in this change — surfacing is via MCP tool response fields and logs only.

## Decisions

### 1. Sequencing: eval-harness → memory-auto-write → temporal-facts → conflict-resolution → agent-namespacing → configurable-reranker → positioning-docs
Each capability after `eval-harness` is validated against it, and `conflict-resolution` requires `temporal-facts` (a contradiction is meaningful only once facts have validity windows) which requires `memory-auto-write` (temporal churn matters most once facts are written automatically, not just at vault-edit cadence). `agent-namespacing` is independent of the temporal/conflict work but touches the same query/storage surface, so it lands after to avoid rebasing churn. `configurable-reranker` is fully independent and low-risk — placed second-to-last as a contained, quick win. `positioning-docs` is last because it depends on eval numbers and the full feature set to describe honestly. Alternative considered: do `configurable-reranker` first as a "quick win" to build momentum — rejected because it has no dependency relationship with anything else and front-loading it would delay the harness that everything else needs for validation.

### 2. Eval harness as a golden-query fixture + CLI, not a live-traffic sampler
Use a curated set of (query, expected note/chunk IDs) pairs stored under `tests/eval/golden_queries.jsonl`, scored by recall@k, MRR, hit-rate. Alternative: instrument production queries and infer relevance from click-through — rejected, there's no click signal (MCP tool calls aren't labeled relevant/irrelevant) and it would require live traffic that doesn't exist yet for a personal tool.

### 3. Memory auto-write as an explicit MCP tool (`write_memory`), not a background listener on conversation transcripts
Clawdiney has no access to raw conversation transcripts (it's an MCP server, not a client) — the calling agent must explicitly call a new `write_memory(fact, source, agent_id)` tool to persist a fact, which runs through fact normalization → entity resolution (existing `ENTITY_RESOLUTION_THRESHOLD`) → dedupe → vault note upsert via `vault_writer`. Alternative: passively parse whatever text is sent through `search_brain` calls as implicit memory — rejected, conflates read and write semantics and creates surprising side effects on a query call.

### 4. Bi-temporal columns on `entities`/`relations` rather than a separate history table
Add `valid_at`, `invalidated_at` (nullable) directly to `entities` and `relations`. A fact with `invalidated_at IS NULL` is current. Alternative: append-only `fact_history` table joined at query time — rejected for this scale (single-user embedded DB); direct columns keep hot-path queries (`get_related_notes`, hybrid search graph joins) simple, and history is still queryable via `invalidated_at IS NOT NULL`.

### 5. Conflict detection at write time, not a background batch job
When `memory-auto-write` or the LLM extraction layer (Layer 2 in `entity_extractor.py`) is about to invalidate/replace a fact about a resolved entity, compare the new value against the current one; if they diverge beyond a normalization-aware threshold, write both with an `is_conflict = 1` marker and an explicit relation `CONTRADICTS` rather than silently invalidating. Alternative: nightly batch job scanning for divergent facts — rejected, delays surfacing and adds a scheduler dependency this project doesn't otherwise need.

### 6. Agent namespacing via a required `agent_id` column, default `"default"` for backward compat
Add `agent_id TEXT NOT NULL DEFAULT 'default'` to `documents`, `entities`, and the new write-path tables; all MCP tools accept an optional `agent_id` param defaulting to `"default"`. Existing single-agent installs are unaffected (everything lands in `"default"`). Alternative: separate `brain.db` per agent — rejected, defeats the embedded-single-file simplicity and blocks cross-agent graph queries (`how_do_projects_relate`-style) that are part of the value proposition.

### 7. Reranker config via `RERANK_MODEL` env var + `ENABLE_RERANK` (already exists) instead of a plugin system
`reranker.py` already lazy-loads a hardcoded model; change it to read `RERANK_MODEL` (default unchanged) so any `sentence-transformers` cross-encoder can be swapped without code changes. Alternative: build a `Reranker` protocol with multiple backend implementations (cross-encoder, LLM-as-judge, none) — rejected as over-engineering for a single-maintainer project; a config string covers the realistic need (try a smaller/faster or larger/slower cross-encoder).

## Risks / Trade-offs

- [Bi-temporal schema change requires migrating existing `brain.db` files] → Ship a versioned migration in `storage.py` (schema_version bump), run automatically on first open, covered by a migration test against a pre-migration fixture DB.
- [Auto-write path could pollute the vault with low-quality extracted facts] → Gate writes through the existing entity-resolution similarity threshold plus a minimum-confidence cutoff; write to a clearly marked `40_Memory/` (or similar) vault area rather than mixing into curated notes, so provenance is visually obvious.
- [Conflict surfacing adds response payload complexity to MCP tools] → Keep it additive/optional: existing tools return unchanged shape by default, conflicts appear only in a new `conflicts` field, and callers that ignore it see no behavior change.
- [`agent_id` default-value migration touches every row of every table] → Since it's `NOT NULL DEFAULT 'default'`, SQLite `ALTER TABLE ADD COLUMN` handles this without a full table rewrite; verified in the migration test.
- [Eval harness golden set can go stale as the vault changes] → Version the golden set alongside a fixture vault snapshot used only for eval runs, decoupled from the user's live vault, so scores stay reproducible in CI.
- [Configurable reranker model swap could silently degrade quality] → Require `RERANK_MODEL` changes to be validated against the eval harness before being adopted as the new default.

## Migration Plan

1. Land `eval-harness` first (no schema change) — establishes baseline scores against current `main` behavior.
2. Land `temporal-facts` schema migration (additive columns, default current-row semantics preserves existing behavior) — re-run eval harness to confirm no regression.
3. Land `memory-auto-write` (new tool, new vault area) — no impact on existing read paths.
4. Land `conflict-resolution` (depends on temporal columns existing) — additive `is_conflict` column + `CONTRADICTS` relation type.
5. Land `agent-namespacing` (additive `agent_id` column, defaults preserve single-agent behavior) — re-run eval harness scoped to `"default"` agent to confirm parity.
6. Land `configurable-reranker` (env var addition, default unchanged).
7. Land `positioning-docs` last, citing eval harness numbers collected from steps 1-6.

Rollback: every schema change is additive (new nullable/defaulted columns, new tables); rollback is dropping the new columns/tables, no destructive migration of pre-existing data at any step.

## Open Questions

- ~~Where in the vault should auto-written memory live~~ **Resolved**: dedicated `40_Memory/` folder, isolated from manually curated notes. Applies when `memory-auto-write` (section 2) is implemented.
- Should `conflict-resolution` block the write (reject until resolved) or always write-and-flag? Current design assumes write-and-flag; revisit if false-positive rate from the eval harness proves too noisy.
- What's the minimum viable golden-query set size for `eval-harness` to be statistically meaningful given this is a single-vault, single-user system?
