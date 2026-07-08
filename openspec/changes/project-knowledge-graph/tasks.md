# Tasks: project-knowledge-graph

## 1. Storage foundation (schema v2 + graph queries)

- [x] 1.1 Add `user_version 1→2` migration in `storage.py`: create `entity_vectors` vec0 table (entity_id, embedding); migration runs in place on existing DBs, tested against a v1 fixture
- [x] 1.2 Add `storage.upsert_typed_entity(vault, name, kind, description, embedding=None)` and `storage.replace_project_relations(vault, project, layer)` (layer selected by confidence: 1.0 = deterministic, <1.0 = semantic)
- [x] 1.3 Add `storage.find_similar_entity(vault, kind, embedding, threshold)` KNN over entity_vectors filtered by kind
- [x] 1.4 Extend `expand_neighborhood` to return entity kind, confidence, and evidence chunk path; add `storage.find_paths(vault, a, b, max_depth=3)` returning up to 5 shortest hop-lists
- [x] 1.5 Tests: v1→v2 migration, typed entity upsert, layer-scoped relation replacement, similarity lookup, mixed-kind expansion, path finding (shared library, no-path, cycle)

## 2. Interfaces parsing + enriched project cards

- [x] 2.1 Create `entity_extractor.py` with layer 1: parse `pyproject.toml`, `package.json`, `docker-compose.yml`, `.env.example` → dataclasses (entities: project/library/service/datastore; relations: DEPENDS_ON/SHARES_DB/CALLS_API_OF; each with source file); malformed files skipped with warning
- [x] 2.2 Interfaces detection: exposes (scripts/bin, compose ports, port literals in entry files) and consumes (datastore URL schemes, env connection vars), each with source file
- [x] 2.3 Extend `project_indexer.generate_markdown`: add Interfaces section (from 2.2) and Purpose/Architecture sections via Ollama (`CARD_LLM_MODEL` config, temperature 0.2), gated by SHA-256 digest of README+manifest+structure stored in card frontmatter; Ollama down → `_pending_` placeholder, digest not stored
- [x] 2.4 Tests: manifest parsing per ecosystem, shared-datastore dedup, interfaces detection with source attribution, card idempotency (no LLM call when digest unchanged — mocked ollama), Ollama-down graceful card

## 3. Layer 1 wiring (deterministic graph population)

- [x] 3.1 `run_extraction(project, storage, provider)`: layer 1 always — write typed entities/relations with confidence 1.0 via `replace_project_relations`
- [x] 3.2 Hook into `watch_projects._do_reindex` and `scripts/index_projects` CLI: run extraction after card generation; failures logged, never break reindex
- [x] 3.3 Tests: end-to-end fixture project → graph rows in tempfile DB; dependency removed from manifest disappears on re-run; other projects' relations untouched

## 4. Layer 2: LLM semantic extraction + entity resolution

- [x] 4.1 LLM extraction: prompt with closed enums, `ollama.generate(format="json", temperature=0)`; parse/validate response, drop invalid items with warning; resolve `quote` → `evidence_chunk_id` by substring match against card chunks (NULL when unmatched); clamp confidence to [0.1, 0.99]
- [x] 4.2 Gate by card content hash in `meta` (`extract_hash:<vault>:<project>`); skip LLM when unchanged
- [x] 4.3 Entity resolution: before insert, embed `"name: description"` and reuse existing entity above `ENTITY_RESOLUTION_THRESHOLD` (default 0.85, new config); below → insert entity + vector
- [x] 4.4 Tests (mocked ollama.generate): valid extraction with evidence, malformed JSON discarded, enum violation discarded, unchanged-hash skips LLM, near-duplicate merged, distinct entity created, re-extraction replaces only semantic layer

## 5. MCP tools

- [x] 5.1 `get_project_card(name, vault=None)`: resolve card note by project name (exact → fragment candidates), return full Markdown + path; unknown → candidate list
- [x] 5.2 `how_do_projects_relate(a, b, vault=None)`: `storage.find_paths` output formatted as hop chains with rel_type, confidence, evidence; no path → clear message; unknown name → names the failing argument
- [x] 5.3 Extend `explore_graph`: non-note entities rendered with kind + rel_type (+ evidence source when present); note-only output unchanged for pure-note neighborhoods
- [x] 5.4 Tests: both tools against tempfile DB fixtures (shared-library path, no-path, unknown project), explore_graph typed output

## 6. Docs, quality, release

- [x] 6.1 Update CLAUDE.md and README: new tools, extraction pipeline, `CARD_LLM_MODEL` / `ENTITY_RESOLUTION_THRESHOLD` config
- [x] 6.2 Full suite green + `ruff check` + `mypy` clean
- [x] 6.3 E2E smoke: run extraction over 2 real projects in `~/Documentos/projetos`, verify `how_do_projects_relate` returns a sane shared-dependency path
