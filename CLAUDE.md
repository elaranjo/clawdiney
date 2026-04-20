# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Overview

Clawdiney is a hybrid Vector + Graph system that transforms an Obsidian Vault into a living knowledge source for AI coding agents. The system enables semantic search and knowledge graph navigation of SOPs, design systems, architectural patterns, and documentation.

## Architecture

The system consists of three main components:

1. **ChromaDB (Vector Database)** - Handles semantic search using embeddings (unified to HTTP client)
2. **Neo4j (Graph Database)** - Manages relationships between notes via WikiLinks
3. **MCP Server** - Provides integration with Claude Code via Model Context Protocol

Data flow:
Obsidian Vault → brain_indexer.py → ChromaDB + Neo4j → brain_mcp_server.py → Claude Code

## Common Development Commands

### Running the System

Start the infrastructure:
```bash
docker compose up -d
```

Index/re-index the Obsidian vault:
```bash
./venv/bin/python3 brain_indexer.py
```

Start the MCP server for Claude Code integration:
```bash
./venv/bin/python3 brain_mcp_server.py
```

Test queries from command line:
```bash
./ask_brain.sh "your query here"
```

Or directly with Python:
```bash
./venv/bin/python3 query_engine.py "your query here"
```

### Development Environment Setup

Initial setup (installs dependencies, starts services, indexes vault):
```bash
chmod +x setup_brain.sh
./setup_brain.sh
```

Manual dependency installation:
```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

### Testing

Run a test query to verify the system is working:
```bash
./venv/bin/python3 query_engine.py "test query"
```

Run unit tests:
```bash
./run_tests.sh
```

Or run tests directly with pytest:
```bash
python -m pytest test_brain_engine.py -v
```

Check Docker services status:
```bash
docker compose ps
```

View logs for troubleshooting:
```bash
docker compose logs neo4j
docker compose logs chromadb
```

## Key Files and Components

- `brain_mcp_server.py` - Main MCP server that integrates with Claude Code (with context manager support)
- `query_engine.py` - Core querying logic with semantic + graph search (unified to HTTP client)
- `brain_indexer.py` - Indexes Obsidian vault content into ChromaDB and Neo4j (unified to HTTP client)
- `config.py` - Centralized configuration management (simplified to HTTP only)
- `setup_brain.sh` - Automated setup script for new installations
- `docker-compose.yml` - Infrastructure definitions for Neo4j and ChromaDB
- `.env` - Configuration file for paths and connection settings (simplified)

## Integration with Claude Code

The system integrates with Claude Code via the Model Context Protocol (MCP). When properly configured in `.claude.json`, Claude Code can use these tools:

1. `search_brain(query)` - Search for architectural patterns, SOPs, and design system components
2. `explore_graph(note_name)` - Find notes related to a specific topic via WikiLinks
3. `read_full_note(filename)` - Read the entire content of a specific note (lists candidates for ambiguous matches)

Configuration example in `~/.claude.json`:
```json
{
  "projects": {
    "/path/to/projects": {
      "mcpServers": {
        "clawdiney": {
          "command": "/path/to/clawdiney/venv/bin/python3",
          "args": ["/path/to/clawdiney/brain_mcp_server.py"]
        }
      }
    }
  }
}
```

## Recent Improvements

For detailed information about recent improvements, see [RELEASE_NOTES.md](RELEASE_NOTES.md).

### Context Manager Support
BrainEngine now supports context manager protocol:
```python
with BrainEngine() as engine:
    result = engine.search("my query")
# Connections are automatically closed
```

### Intelligent File Resolution
When multiple files match a name, read_note now lists all candidates:
```
Multiple files found for 'design.md' (3 matches):
- frontend/design.md
- backend/design.md
- mobile/design.md

Please specify which file you want to read.
```