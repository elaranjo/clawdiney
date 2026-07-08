# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Clawdiney is a hybrid Vector + Graph system that transforms an Obsidian Vault into a living knowledge source for AI coding agents. The system enables semantic search and knowledge graph navigation of SOPs, design systems, architectural patterns, and documentation.

## Architecture

The system is fully embedded (v0.2.0) — a single SQLite database (`brain.db`) holds everything:

1. **sqlite-vec** - Vector KNN search (embeddings via Ollama `bge-m3`)
2. **FTS5** - BM25 full-text search (exact terms, acronyms, identifiers)
3. **Graph tables** (`entities`, `relations`) - Note relationships via WikiLinks and shared tags
4. **MCP Server** - Provides retrieval-first integration via Model Context Protocol

Search is hybrid: BM25 + vector results fused with Reciprocal Rank Fusion (k=60), optionally reranked by a cross-encoder (`BAAI/bge-reranker-v2-m3`, optional extra `clawdiney[rerank]`).

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
│   ├── mcp_server.py         # MCP server for AI agents
│   ├── config.py             # Configuration management
│   ├── chunking.py           # Text chunking strategies
│   ├── project_indexer.py    # Analyze codebases → Obsidian docs
│   ├── project_index_config.py # Selective indexing patterns
│   ├── rag_optimizer.py      # Query preprocessing
│   ├── constants.py          # Application constants
│   ├── logging_config.py     # Logging setup
│   └── scripts/
│       ├── watch_vault.py    # File watcher for real-time sync
│       ├── sync_vault.py     # Manual sync script
│       └── index_projects.py # CLI: index projects to Obsidian
├── tests/                    # Test suite (pytest)
├── scripts/                  # Shell scripts
├── docker/                   # Docker configuration
├── SECURITY_REVIEW.md        # Security audit documentation
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
- `src/clawdiney/project_indexer.py` - Analyzes codebases and generates Obsidian docs
- `src/clawdiney/project_index_config.py` - Selective file indexing patterns (include/exclude)

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

## Integration

The system integrates with MCP clients. When properly configured, the agent should use these tools:

1. `search_brain(query)` - Search for architectural patterns, SOPs, and design system components
2. `explore_graph(note_name)` - Find notes related to a specific topic via WikiLinks
3. `resolve_note(name)` - Resolve ambiguous note names into canonical vault-relative paths
4. `get_note_chunks(path)` - Inspect indexed chunk headers for a resolved note

The intended workflow is:
- use `search_brain` first
- use `resolve_note` when a note name is ambiguous
- use `get_note_chunks` for structured drill-down
- read the full file directly from the vault or repository when needed

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

### Project Indexer (NEW - feature/project-indexer)
- Analyzes Python and Node.js projects
- Generates standardized Markdown docs for Obsidian
- Selective file indexing with include/exclude patterns
- Security: path traversal prevention, filename sanitization
- 12 unit tests with 100% pass rate
- See `SECURITY_REVIEW.md` for audit details
