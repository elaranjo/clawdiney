# Design: project-knowledge-graph

## Context

v0.2.0 delivered the embedded store with a graph schema built for this change: `entities(kind, description)`, `relations(rel_type, confidence, evidence_chunk_id)`. Today only `note`/`tag` kinds and `LINKS_TO`/`HAS_TAG` relations are populated by vault parsing. `project_indexer.py` already scans `~/Documentos/projetos`, detects Python/Node projects, and generates Markdown docs (stack, structure, commands, entry points) into the vault; `watch_projects.py` re-runs it on changes with debounce. Ollama is available for both embeddings and generation.

Scale: ~6-15 projects. LLM extraction cost is one call per changed project card — negligible.

## Goals / Non-Goals

**Goals:**
- Project cards with Purpose/Architecture (LLM) and Interfaces (deterministic) sections.
- Layer 1: manifest parsing → typed entities/relations, confidence 1.0.
- Layer 2: LLM extraction from cards → semantic relations with confidence + evidence, gated by card content hash.
- Entity resolution by embedding similarity (no duplicate "JWT" / "jwt auth").
- MCP tools `get_project_card`, `how_do_projects_relate`; richer `explore_graph` output.

**Non-Goals:**
- Indexing raw source code line-by-line (agentic grep remains the tool for that).
- Community detection / PageRank (no networkx yet).
- Cross-vault entity linking (entities stay vault-scoped).
- Extraction from arbitrary vault notes (cards only, this change).

## Decisions

### D1: New module `entity_extractor.py`, both layers in one file
Layer 1 (`extract_from_manifests(project_path)`) returns dataclasses; layer 2 (`extract_semantic(card_content, ...)`) calls Ollama. A thin `run_extraction(project, storage, provider)` orchestrates: layer 1 always, layer 2 only on card-hash change (hash stored in `meta` table as `extract_hash:<vault>:<project>`). Storage writes go through new `storage.py` methods — the extractor holds no SQL.

**Alternative rejected**: folding extraction into `project_indexer.py` — that module is about generating docs; extraction reads docs + manifests and writes graph rows. Different responsibilities, different test seams.

### D2: Layer boundaries by `confidence`
Layer 1 relations: `confidence = 1.0`. Layer 2: model confidence clamped to `[0.1, 0.99]`. Re-extraction deletes prior relations for that project *by layer* (`confidence = 1.0` vs `< 1.0` distinguishes them — no schema change needed) before inserting fresh ones. Deterministic and semantic knowledge never clobber each other.

### D3: LLM contract — closed enum, JSON, discard-invalid
Prompt asks for `{"entities": [{"name", "kind", "description"}], "relations": [{"source", "target", "rel_type", "confidence", "quote"}]}` with `kind ∈ {service, library, pattern, datastore, concept}` and `rel_type ∈ {USES_PATTERN, IMPLEMENTS, MENTIONS, CALLS_API_OF}`. Response parsed with `json.loads` after stripping code fences; items failing enum/shape validation are dropped and logged. `quote` is matched against card chunks (substring) to resolve `evidence_chunk_id`; unmatched quotes → relation kept with NULL evidence. Uses `ollama.generate` with `format="json"` and temperature 0.

### D4: Entity resolution — embedding similarity over name+description
New `storage.find_similar_entity(vault, kind, name, description, embedding, threshold)`: embed `"{name}: {description}"`, KNN against a new small vec table `entity_vectors(entity_id, embedding)` filtered by kind, cosine threshold default 0.85 (configurable `ENTITY_RESOLUTION_THRESHOLD`). Below threshold → insert new entity + its vector. Layer-1 entities (exact names from manifests) skip resolution — they match by `UNIQUE(vault, name, kind)` naturally.

Schema addition (backward-compatible migration to `user_version = 2`): create `entity_vectors` vec0 table if missing. Existing brain.db files migrate in place — no re-index.

### D5: Interfaces parsing (deterministic, per ecosystem)
- Exposes: `pyproject [project.scripts]`, `package.json scripts/bin`, `docker-compose ports`, FastMCP/uvicorn/express port literals in entry files (regex over entry points only, not the whole tree).
- Consumes: URLs/hosts/ports in `.env.example` and docker-compose `environment`/`depends_on`; known datastore schemes (`postgres://`, `redis://`, `mongodb://`, `bolt://`, `sqlite:`).
Each item records its source file for the card and for relation evidence.

### D6: Card Purpose/Architecture via Ollama, cached by input digest
Digest = SHA-256 of (README head + manifest + structure listing). Stored in the card's frontmatter (`clawdiney_digest`). Regenerate LLM sections only when digest changes; otherwise reuse previous sections (parsed from the existing card). Ollama down → sections rendered as `_pending (Ollama unavailable)_`, digest not stored, retried next run. Generation model configurable via `CARD_LLM_MODEL` (default: `qwen3` fallback to any available); temperature 0.2, ~300 token cap per section.

### D7: Path finding for `how_do_projects_relate`
Bidirectional BFS is overkill at this scale; reuse the recursive-CTE walk from `expand_neighborhood` extended to track path (`path` as JSON array of relation ids, depth ≤ 3), then reconstruct hops with a join. Return up to 5 shortest paths. Implemented as `storage.find_paths(vault, a, b, max_depth=3)`.

### D8: Watcher integration
`watch_projects.py` already re-indexes a project on change; append `run_extraction(project)` to `_do_reindex`. Extraction failures log and never break the reindex loop.

## Risks / Trade-offs

- [LLM extraction quality varies by local model] → closed enums + confidence stored + evidence quotes; consumers can filter by confidence; bad items are droppable data, not code paths.
- [Entity resolution threshold wrong → merges distinct things or splits duplicates] → configurable threshold, resolution only for layer-2 kinds, evidence preserved so mistakes are auditable; start conservative (0.85).
- [entity_vectors migration on existing DBs] → additive `user_version 1→2` migration with `CREATE VIRTUAL TABLE IF NOT EXISTS`; tested against a v1 fixture DB.
- [Regex port/URL parsing false positives] → scoped to entry points and config files only; every item carries its source file so noise is visible and cheap to ignore.
- [Card LLM sections drift from reality] → digest-gated regeneration keeps them tied to deterministic inputs; sections labeled as generated.

## Migration Plan

1. Storage migration v2 (entity_vectors) lands first — no behavior change.
2. Card enrichment + layer 1 ship together (deterministic, safe).
3. Layer 2 + resolution + MCP tools last.
4. Rollback: extracted rows are identifiable (`kind != 'note'/'tag'`) — a cleanup SQL removes them without touching vault data.

## Open Questions

- `CARD_LLM_MODEL` default: pick the best small local model at implementation time (check `ollama list`); must handle JSON mode.
- Should `how_do_projects_relate` also search card text for co-mentions when no graph path exists? (Proposed: no — keep tool semantics pure graph; agent can `search_brain` separately.)
