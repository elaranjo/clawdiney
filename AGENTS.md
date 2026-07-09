# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Repository Overview

Clawdiney is a hybrid Vector + Graph system that transforms an Obsidian Vault into a living knowledge source for AI coding agents. The system enables semantic search and knowledge graph navigation of SOPs, design systems, architectural patterns, and documentation.

## Architecture

The system is fully embedded (v0.2.0) — a single SQLite database (`brain.db`) holds everything:

1. **sqlite-vec** - Vector KNN search (embeddings via Ollama `bge-m3`)
2. **FTS5** - BM25 full-text search (exact terms, acronyms, identifiers)
3. **Graph tables** (`entities`, `relations`) - Note relationships via WikiLinks and shared tags
4. **MCP Server** - Provides integration with Codex via Model Context Protocol

Data flow:
Obsidian Vault → `src/clawdiney/indexer.py` → `brain.db` (via `storage.py`) → `src/clawdiney/mcp_server.py` → Codex

**No Docker services required.** Only Ollama must be running (embeddings). The database lives at `BRAIN_DB_PATH` (default `~/.clawdiney/brain.db`).

## Common Development Commands

### Running the System

No infrastructure to start — storage is an embedded SQLite file. Ensure Ollama is running with the `bge-m3` model pulled.

Index/re-index the Obsidian vault:
```bash
./venv/bin/python3 -m clawdiney.indexer
```

Start the MCP server for Codex integration:
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

Initial setup (installs dependencies, indexes vault):
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

- `src/clawdiney/mcp_server.py` - Main MCP server that integrates with Codex
- `src/clawdiney/query_engine.py` - Hybrid retrieval (BM25 + vector + RRF) + rerank + graph expansion
- `src/clawdiney/storage.py` - Single gateway to `brain.db` (schema, hybrid search SQL, graph queries)
- `src/clawdiney/indexer.py` - Full indexing of Obsidian vault into `brain.db`
- `src/clawdiney/config.py` - Centralized configuration management
- `scripts/setup_brain.sh` - Automated setup script for new installations
- `.env` - Configuration file for paths and settings

## Integration with MCP Clients

The system integrates via the Model Context Protocol (MCP). When properly configured, the agent has access to **read and write** tools:

### Read Tools (Discovery)

1. `search_brain(query)` - Search for architectural patterns, SOPs, and design system components
2. `explore_graph(note_name)` - Find notes related to a specific topic via WikiLinks and shared tags
3. `resolve_note(name)` - Resolve ambiguous note names to canonical vault-relative paths
4. `get_note_chunks(path)` - List chunk headers for a note (structured preview)
5. `get_project_card(name)` - Full project card (Purpose, Stack, Architecture, Interfaces)
6. `how_do_projects_relate(a, b)` - Graph paths between two projects
7. `health_check()` - Check health status of `brain.db` and Ollama

### Write Tools (Knowledge Capture)

8. `write_note(path, content, mode)` - Create or update a note at any vault location
   - `mode`: "create" (fail if exists), "overwrite" (replace), "append" (add to end)
9. `append_to_daily(content)` - Append content to today's daily note (50_Daily/YYYY-MM-DD.md)
10. `add_learning(topic, content, area)` - Save learnings to appropriate folder
   - `area`: "SOPs", "Architecture", "DesignSystem", "Projects", "Areas", "Learnings"
11. `delete_note(path)` - Delete a note and remove from index

### Example Workflow

```python
# 1. Search for existing patterns
search_brain("backend API deployment")

# 2. If found, update the SOP
write_note("30_Resources/SOPs/SOP_Deploy.md", updated_content, mode="append")

# 3. If not found, create new learning
add_learning("Backend_API_Deploy", "# SOP\\n\\nDeployment pattern...", area="SOPs")

# 4. Document daily learnings
append_to_daily("## Learnings\\n- Discovered X about the architecture")
```

### Configuration Example

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

See [CLAUDE.md](CLAUDE.md) "Recent Improvements" for the full history of the embedded storage migration (v0.2.0) and project knowledge graph features.
