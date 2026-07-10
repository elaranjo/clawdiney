# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Clawdiney is a hybrid Vector + Graph system that transforms an Obsidian Vault into a living knowledge source for AI coding agents. The system enables semantic search and knowledge graph navigation of SOPs, design systems, architectural patterns, and documentation.

## Architecture

The system is fully embedded (v0.2.0) — a single SQLite database (`brain.db`, schema v5) holds everything:

1. **sqlite-vec** - Vector KNN search (embeddings via Ollama `bge-m3`)
2. **FTS5** - BM25 full-text search (exact terms, acronyms, identifiers)
3. **Graph tables** (`entities`, `relations`) - Note relationships via WikiLinks and shared tags, bi-temporal (`valid_at`/`invalidated_at`) with conflict tracking (`is_conflict`, `CONTRADICTS`) for the LLM-extracted semantic layer, and per-agent namespaced (`agent_id`, default `"default"`)
4. **MCP Server** - Provides retrieval-first integration via Model Context Protocol, plus a `write_memory` tool for agent-written memory

Search is hybrid: BM25 + vector results fused with Reciprocal Rank Fusion (k=60), optionally reranked by a cross-encoder (default `BAAI/bge-reranker-v2-m3`, configurable via `RERANK_MODEL`, optional extra `clawdiney[rerank]`).

Data flow:
Obsidian Vault → `src/clawdiney/indexer.py` → `brain.db` (via `storage.py`) → `src/clawdiney/mcp_server.py` → MCP client

**No Docker services required.** Only Ollama must be running (embeddings). The database lives at `BRAIN_DB_PATH` (default `~/.clawdiney/brain.db`).

## Project Structure

```
clawdiney/
├── src/clawdiney/            # Main Python package
│   ├── storage.py            # Embedded SQLite gateway (sqlite-vec + FTS5 + graph)
│   ├── indexer.py            # Full indexing into brain.db
│   ├── incremental_indexer.py # Incremental sync (content hashes in brain.db)
│   ├── query_engine.py       # Hybrid search (BM25 + vector, RRF fusion)
│   ├── reranker.py           # Cross-encoder reranking (optional extra)
│   ├── embedding_providers.py # EmbeddingProvider protocol (Ollama/OpenAI)
│   ├── vault_writer.py       # Thread-safe write operations
│   ├── memory_writer.py      # write_memory: fact normalization + agent-scoped entity resolution
│   ├── mcp_server.py         # MCP server for AI agents
│   ├── config.py             # Configuration management
│   ├── chunking.py           # Text chunking strategies
│   ├── project_indexer.py    # Analyze codebases → Obsidian docs
│   ├── project_index_config.py # Selective indexing patterns
│   ├── rag_optimizer.py      # Query preprocessing
│   ├── constants.py          # Application constants
│   ├── logging_config.py     # Logging setup
│   ├── eval/                 # Retrieval eval harness (recall@k/MRR/hit-rate, clawdiney-eval CLI)
│   └── scripts/
│       ├── watch_vault.py    # File watcher for real-time sync
│       ├── sync_vault.py     # Manual sync script
│       └── index_projects.py # CLI: index projects to Obsidian
├── tests/                    # Test suite (pytest)
├── tests/eval/                # Eval harness fixture vault, golden queries, baseline
├── scripts/                  # Shell scripts
├── docker/                   # Docker configuration
├── SECURITY_REVIEW.md        # Security audit documentation
├── BENCHMARKS.md              # Retrieval eval numbers and reranker latency/precision trade-offs
└── pyproject.toml            # Python project configuration
```

## Common Development Commands

### Running the System

No infrastructure to start — storage is an embedded SQLite file. Ensure Ollama is running with the `bge-m3` model pulled.

Index/re-index the Obsidian vault:
```bash
./venv/bin/python3 -m clawdiney.indexer
```

Start the MCP server for Claude Code integration:
```bash
./venv/bin/python3 -m clawdiney.mcp_server
```

Test queries from command line:
```bash
./scripts/ask_brain.sh "your query here"
```

Or directly with Python:
```bash
./venv/bin/python3 -m clawdiney.query_engine "your query here"
```

Run the retrieval eval harness (recall@k / MRR / hit-rate against a fixture vault, regression-gated against `tests/eval/baseline.json`; requires Ollama running):
```bash
./venv/bin/clawdiney-eval --all-modes
```

### Project Indexer (New!)

Index your codebases and generate documentation for Obsidian:

```bash
# Preview what would be indexed
./scripts/index_projects.sh ~/Documentos/projetos --dry-run

# Index all projects (generates .md files in Obsidian)
./scripts/index_projects.sh ~/Documentos/projetos

# Or using Python directly
./venv/bin/python3 -m clawdiney.scripts.index_projects ~/Documentos/projetos
```

This analyzes projects (Python, Node.js) and creates notes with:
- Tech stack and dependencies
- Directory structure
- Main commands/scripts
- Entry points

### Auto-Sync Watcher (NEW!)

Keep Obsidian docs automatically synchronized with code changes:

```bash
# Start watcher in background
./scripts/start_watcher.sh

# Stop watcher
./scripts/stop_watcher.sh

# View live logs
tail -f logs/watcher.log
```

**What it does:**
- Monitors `/home/ermanelaranjo/Documentos/projetos` for file changes
- Auto-detects changes in `.py`, `.ts`, `.js`, `.json`, `.toml`, `.yaml`, `.md`, etc.
- Reindexes affected projects after 10s debounce (batches rapid changes)
- High-priority for `package.json`, `pyproject.toml`, `requirements.txt`, etc.
- Ignores `node_modules`, `__pycache__`, `venv`, `.git`, `dist`, `build`, etc.

**Install as systemd service (auto-start on boot):**

```bash
# Copy service file
sudo cp scripts/clawdiney-watcher.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable clawdiney-watcher
sudo systemctl start clawdiney-watcher

# Check status
sudo systemctl status clawdiney-watcher

# View logs
journalctl -u clawdiney-watcher -f
```

### Development Environment Setup

Initial setup (installs dependencies, starts services, indexes vault):
```bash
chmod +x scripts/setup_brain.sh
./scripts/setup_brain.sh
```

Manual dependency installation:
```bash
python3 -m venv venv
./venv/bin/pip install -e .
```

### Testing

Run a test query to verify the system is working:
```bash
./venv/bin/python3 -m clawdiney.query_engine "test query"
```

Run unit tests:
```bash
./scripts/run_tests.sh
```

Or run tests directly with pytest:
```bash
./venv/bin/python3 -m pytest tests/ -v
```

Use the MCP `health_check` tool (or open `brain.db` with any SQLite client) for troubleshooting.

## Key Files and Components

### Core Modules
- `src/clawdiney/storage.py` - Single gateway to `brain.db` (schema, hybrid search SQL, graph queries)
- `src/clawdiney/mcp_server.py` - MCP server exposing retrieval and note-resolution tools
- `src/clawdiney/query_engine.py` - Hybrid retrieval (BM25 + vector + RRF) + rerank + graph expansion
- `src/clawdiney/indexer.py` - Full indexing of Obsidian vault into brain.db
- `src/clawdiney/incremental_indexer.py` - Incremental sync (SHA-256 hashes stored in brain.db)
- `src/clawdiney/reranker.py` - Cross-encoder reranker (lazy-loaded, optional extra)
- `src/clawdiney/embedding_providers.py` - EmbeddingProvider protocol; Ollama (`ollama.embed`) default
- `src/clawdiney/vault_writer.py` - Thread-safe vault write operations
- `src/clawdiney/memory_writer.py` - `write_memory`: normalizes a fact into subject/predicate/value, resolves the subject against agent-scoped entities, upserts into a provenance-marked `40_Memory/` note
- `src/clawdiney/project_indexer.py` - Analyzes codebases and generates Obsidian docs
- `src/clawdiney/project_index_config.py` - Selective file indexing patterns (include/exclude)
- `src/clawdiney/eval/` - Retrieval eval harness: `metrics.py` (recall@k/MRR/hit-rate), `harness.py` (fixture indexing + scoring), `cli.py` (`clawdiney-eval`)

### Supporting Modules
- `src/clawdiney/config.py` - Centralized configuration management (`BRAIN_DB_PATH`, `EMBEDDING_PROVIDER`, `EMBEDDING_DIMENSION`)
- `src/clawdiney/chunking.py` - Text chunking strategies (headers, fixed-size)
- `src/clawdiney/rag_optimizer.py` - Query preprocessing
- `src/clawdiney/constants.py` - Application-wide constants
- `src/clawdiney/logging_config.py` - Logging setup

### Infrastructure
- `brain.db` (at `BRAIN_DB_PATH`, default `~/.clawdiney/brain.db`) - The entire datastore
- `.env` - Configuration file for paths and settings
- `docker/docker-compose.yml` - **Legacy (pre-0.2.0)**, no longer required

### Documentation
- `SECURITY_REVIEW.md` - Security audit and best practices
- `CLAUDE.md` - This file (development guide)
- `README.md` - User-facing documentation
- `BENCHMARKS.md` - Retrieval eval numbers (recall@k/MRR/hit-rate per mode) and reranker model latency/precision trade-offs

## Integration

The system integrates with MCP clients. When properly configured, the agent should use these tools:

1. `search_brain(query, vault?, agent_id?)` - Search for architectural patterns, SOPs, and design system components. `agent_id` (optional) also includes that agent's own memory (see `write_memory`) alongside shared content; the response appends an "Unresolved conflicts" section when returned notes touch a contradicted fact
2. `explore_graph(note_name, vault?, agent_id?)` - Find related entities (notes, projects, libraries, patterns) with typed relations and evidence; same `agent_id` scoping and conflict surfacing as `search_brain`
3. `resolve_note(name)` - Resolve ambiguous note names into canonical vault-relative paths
4. `get_note_chunks(path)` - Inspect indexed chunk headers for a resolved note
5. `get_project_card(name)` - Full project card (Purpose, Stack, Architecture, Interfaces) — first call when touching an unfamiliar project
6. `how_do_projects_relate(a, b, vault?, agent_id="*")` - Graph paths between two projects (shared libraries, datastores, patterns) with evidence. `agent_id="*"` (default) applies no filtering; pass a specific id for an explicit cross-namespace opt-in
7. `write_memory(fact, source, agent_id="default", vault?)` - Persist a natural-language fact (ideally `"<Subject> <verb> <value>"`) as agent-written memory. This is the only tool that turns conversation/agent knowledge into vault content — read tools never write as a side effect

The intended workflow is:
- use `search_brain` first
- use `resolve_note` when a note name is ambiguous
- use `get_note_chunks` for structured drill-down
- read the full file directly from the vault or repository when needed
- use `write_memory` to persist a fact learned during the conversation for future sessions

Note: `resolve_note`, `get_note_chunks`, and `get_project_card` resolve notes via filesystem glob over the vault, not the `documents`/`entities` tables — they have no `agent_id` parameter since there's no per-agent data to filter there.

Configuration example in `~/.claude.json`:
```json
{
  "projects": {
    "/path/to/projects": {
      "mcpServers": {
        "clawdiney": {
          "command": "/path/to/clawdiney/venv/bin/python3",
          "args": ["-m", "clawdiney.mcp_server"]
        }
      }
    }
  }
}
```

## Recent Improvements

### Package Structure (v0.1.0)
- Project reorganized as proper Python package (`src/clawdiney/`)
- Installable with `pip install -e .`
- All imports use relative imports within the package

### Embedded Storage Migration (v0.2.0)
- Neo4j + ChromaDB + Redis replaced by a single SQLite file (`brain.db`)
- Hybrid search: BM25 (FTS5) + vector KNN (sqlite-vec) fused with RRF (k=60)
- Cross-encoder reranking (`BAAI/bge-reranker-v2-m3`) replaces LLM-generative scoring
- All embeddings flow through `EmbeddingProvider` (`ollama.embed` API)
- Per-note atomic index updates (single transaction: chunks + vectors + FTS + graph)

### Incremental Indexing
- SHA-256 content hashes stored in `brain.db` (`documents.content_hash`)
- Only re-index changed files; deletions cascade through all derived rows

### Security Enhancements
- Path validation with symlink resolution
- Prevents symlink traversal attacks
- FTS5 query sanitization (hostile agent input cannot break MATCH syntax)

### Project Indexer
- Analyzes Python and Node.js projects
- Generates standardized Markdown docs for Obsidian
- Selective file indexing with include/exclude patterns
- Security: path traversal prevention, filename sanitization
- See `SECURITY_REVIEW.md` for audit details

### Project Knowledge Graph (v0.2.x)
- **Enriched project cards**: Purpose/Architecture (LLM via Ollama, `CARD_LLM_MODEL`, digest-gated regeneration) + Interfaces (exposes/consumes, parsed deterministically with source attribution)
- **Entity extraction** (`entity_extractor.py`), two layers:
  - Layer 1 (deterministic, confidence 1.0): manifests → `library`/`service`/`datastore` entities, `DEPENDS_ON`/`SHARES_DB`/`CALLS_API_OF` relations
  - Layer 2 (LLM, confidence < 1.0): project cards → `USES_PATTERN`/`IMPLEMENTS`/`MENTIONS` relations with evidence chunks; gated by card content hash
- **Entity resolution**: embedding similarity over `entity_vectors` (threshold `ENTITY_RESOLUTION_THRESHOLD`, default 0.85) prevents duplicates
- Layers never clobber each other (re-extraction replaces only its own layer)
- Runs automatically after `index_projects` / project watcher reindex

### Retrieval Eval Harness (v0.3.x)
- `clawdiney-eval` CLI scores retrieval quality (recall@k, MRR, hit rate) against a fixture vault (`tests/eval/fixture_vault/`, decoupled from the user's live vault) and a golden-query set (`tests/eval/golden_queries.jsonl`)
- Modes: hybrid / BM25-only / vector-only, rerank on/off — isolates each retrieval component's contribution
- `--update-baseline` records `tests/eval/baseline.json`; default run exits non-zero on regression beyond `--tolerance` (default 0.05)
- See `BENCHMARKS.md` for current numbers and the reranker model comparison

### Memory Auto-Write (v0.3.x)
- `write_memory` MCP tool (`memory_writer.py`): the only entry point that turns agent/conversation text into vault content — read tools (`search_brain`, `explore_graph`, ...) never write as a side effect
- Normalizes `"<Subject> <verb> <value>"` into subject/predicate/value (heuristic regex match on known verbs; confidence 1.0 on match, 0.4 fallback); rejects writes below `MEMORY_MIN_CONFIDENCE` (default 0.3)
- Subject resolved against existing entities via the same embedding-similarity threshold as the project knowledge graph; writes to a provenance-marked `40_Memory/<Subject>.md` note (one note per resolved subject, one bullet per predicate); a duplicate fact is a no-op, a changed value updates the bullet in place

### Bi-Temporal Fact Tracking (v0.3.x, schema v3)
- `entities`/`relations` carry `valid_at`/`invalidated_at`; a row with `invalidated_at IS NULL` is the current fact
- Supersede semantics (invalidate old row, insert new) apply to the semantic/LLM relations layer (`replace_project_relations`), where facts genuinely change value between extraction runs — WikiLink/tag relations stay hard-delete-and-reinsert since they mirror file content 1:1 (derived structure, not asserted facts)
- `get_related_notes`, `expand_neighborhood`, `find_paths`, and `BrainQueryEngine.query`'s graph expansion accept an optional `as_of` timestamp for historical queries; default (no `as_of`) considers only currently-valid facts — not currently exposed through any MCP tool

### Conflict Detection & Resolution (v0.3.x, schema v4)
- `entities`/`relations` carry `is_conflict`; a `CONTRADICTS` relation links two entities asserted as contradictory values for the same (source, rel_type) slot
- Detected in the semantic relations layer: when a slot is reasserted with a different target within one extraction run, both facts stay current (flagged, not invalidated) instead of one silently overwriting the other
- `BrainStorage.get_conflicts`/`resolve_conflict` read/resolve; `search_brain`/`explore_graph` MCP responses append an "Unresolved conflicts" section when relevant

### Agent Namespacing (v0.3.x, schema v5)
- `documents`/`entities` carry `agent_id` (default `"default"`); `entities`' uniqueness widened to `(vault, agent_id, name, kind)` so different agents can have same-named entities without colliding
- Write path (`indexer` → `IncrementalIndexer` → `VaultWriter` → `memory_writer`) threads `agent_id` end to end; non-default agents' memory notes land in their own `40_Memory/<agent_id>/` subfolder
- `search_brain`/`explore_graph` accept optional `agent_id`, scoping to that agent's data plus shared (`"default"`) content; `how_do_projects_relate` requires an explicit `agent_id` opt-in for cross-namespace graph queries (currently a no-op since project/dependency entities aren't agent-scoped)

### Configurable Reranker (v0.3.x)
- `RERANK_MODEL` (default `BAAI/bge-reranker-v2-m3`, unchanged) selects any `sentence-transformers`-compatible cross-encoder without code changes
- See `BENCHMARKS.md` for the measured latency delta of a smaller alternative (`cross-encoder/ms-marco-MiniLM-L-6-v2`) — validate any non-default model against the eval harness before adopting it as the new default
