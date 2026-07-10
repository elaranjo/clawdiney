## Why

Clawdiney is architecturally lean (single embedded SQLite file, no service sprawl) but functionally behind memory-layer peers (mem0, Zep/Graphiti, Letta/MemGPT, Cognee): it only reads a vault passively, has no automatic write path, no temporal/episodic model, no contradiction handling, no multi-agent isolation, and no benchmark proving hybrid search + rerank actually earns their cost. Without these, it stays a "RAG over Obsidian" tool rather than a competitive agent-memory system.

## What Changes

- Add an evaluation harness (retrieval metrics: recall@k, MRR, hit rate) so every subsequent change below is measured, not assumed.
- Add an automatic memory write path: conversations/agent output → fact extraction → dedupe against existing entities → vault note update, instead of manual `vault_writer` calls only.
- Add bi-temporal fact tracking (`valid_at` / `invalidated_at`) on `relations`/`entities` so facts can change over time without being silently overwritten.
- Add contradiction/conflict detection when two sources disagree about the same resolved entity, surfaced instead of silently picking one.
- Add per-agent/per-namespace isolation (`agent_id` scoping) on read and write paths so multiple agents/projects don't bleed context into each other.
- Make the reranker model configurable (currently hardcoded to `BAAI/bge-reranker-v2-m3`) with a documented latency/precision trade-off, including a no-rerank fast path.
- Rewrite positioning docs (README) to lead with the embedded-SQLite footprint advantage vs. Neo4j+Chroma+Redis-style peer stacks, backed by the new eval harness numbers.

**BREAKING**: bi-temporal fact tracking changes the `relations`/`entities` schema — requires a migration for existing `brain.db` files.

## Capabilities

### New Capabilities
- `eval-harness`: retrieval evaluation framework (golden query set, recall@k/MRR/hit-rate metrics, CLI runner, regression gate) used to validate all later changes.
- `memory-auto-write`: automatic fact-extraction pipeline that turns conversational/agent input into vault note writes, deduped via existing entity resolution.
- `temporal-facts`: bi-temporal validity tracking for graph facts (`valid_at`/`invalidated_at`), with query-time "as of" support.
- `conflict-resolution`: detection and surfacing of contradictory facts about the same resolved entity, building on `temporal-facts` and existing entity resolution.
- `agent-namespacing`: per-agent/per-namespace scoping (`agent_id`) across storage, indexer, and MCP query paths.
- `configurable-reranker`: pluggable reranker model selection plus a no-rerank fast path, exposed via config.

### Modified Capabilities
- `hybrid-search`: query paths gain `agent_id` scoping (`agent-namespacing`) and optional "as of" temporal filtering (`temporal-facts`); reranker stage becomes configurable (`configurable-reranker`).
- `graph-store`: `entities`/`relations` schema gains bi-temporal columns (`temporal-facts`) and conflict metadata (`conflict-resolution`).

## Impact

- **Schema**: `storage.py` — new columns/tables for temporal validity and conflicts; migration path for existing `brain.db`.
- **New modules**: eval harness (`src/clawdiney/eval/`), fact-extraction pipeline (extends `entity_extractor.py`), conflict resolver.
- **Modified modules**: `query_engine.py` (agent scoping, temporal filter, reranker config), `reranker.py` (pluggable model), `mcp_server.py` (agent_id param on tools), `vault_writer.py` (auto-write entry point).
- **Docs**: `README.md`, `CLAUDE.md` updated with new capabilities and eval numbers.
- **Dependencies**: no new required deps; reranker config may reference alternate `sentence-transformers` models already covered by the `rerank` extra.
