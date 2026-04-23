# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Clawdiney is a hybrid Vector + Graph system that transforms an Obsidian Vault into a living knowledge source for AI coding agents. The system enables semantic search and knowledge graph navigation of SOPs, design systems, architectural patterns, and documentation.

## Architecture

The system consists of three main components:

1. **ChromaDB (Vector Database)** - Handles semantic search using embeddings (unified to HTTP client)
2. **Neo4j (Graph Database)** - Manages relationships between notes via WikiLinks
3. **MCP Server** - Provides retrieval-first integration via Model Context Protocol

Data flow:
Obsidian Vault → `src/clawdiney/indexer.py` → ChromaDB + Neo4j → `src/clawdiney/mcp_server.py` → MCP client

## Project Structure

```
clawdiney/
├── src/clawdiney/            # Main Python package
│   ├── indexer.py            # Full indexing (ChromaDB + Neo4j)
│   ├── incremental_indexer.py # Incremental sync with state tracking
│   ├── query_engine.py       # Hybrid search (vector + graph)
│   ├── vault_writer.py       # Thread-safe write operations
│   ├── mcp_server.py         # MCP server for AI agents
│   ├── config.py             # Configuration management
│   ├── chunking.py           # Text chunking strategies
│   └── scripts/
│       ├── watch_vault.py    # File watcher for real-time sync
│       └── sync_vault.py     # Manual sync script
├── tests/                    # Test suite
├── scripts/                  # Shell scripts
├── docker/                   # Docker configuration
└── pyproject.toml            # Python project configuration
```

## Common Development Commands

### Running the System

Start the infrastructure:
```bash
docker compose -f docker/docker-compose.yml up -d
```

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

Check Docker services status:
```bash
docker compose -f docker/docker-compose.yml ps
```

View logs for troubleshooting:
```bash
docker compose -f docker/docker-compose.yml logs neo4j
docker compose -f docker/docker-compose.yml logs chromadb
```

## Key Files and Components

- `src/clawdiney/mcp_server.py` - MCP server exposing retrieval and note-resolution tools
- `src/clawdiney/query_engine.py` - Core querying logic with semantic + graph search
- `src/clawdiney/indexer.py` - Indexes Obsidian vault content into ChromaDB and Neo4j
- `src/clawdiney/incremental_indexer.py` - Incremental sync with SHA-256 state tracking
- `src/clawdiney/vault_writer.py` - Thread-safe vault write operations
- `src/clawdiney/config.py` - Centralized configuration management
- `docker/docker-compose.yml` - Infrastructure definitions for Neo4j and ChromaDB
- `.env` - Configuration file for paths and connection settings

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

### Incremental Indexing
- State tracking with SHA-256 file hashes
- Only re-index changed files
- Atomic state file writes

### Neo4j Performance Fix
- `sync_graph()` now supports incremental mode
- O(1) per-note relationship updates instead of O(n²) full rebuild

### Security Enhancements
- Path validation with symlink resolution
- Prevents symlink traversal attacks
