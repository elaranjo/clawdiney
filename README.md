# 🧠 Clawdiney

**Expanded Brain for Coding Agents**

A hybrid **Vector + Graph** system that transforms your Obsidian vaults into a living knowledge source for AI coding agents.

<p align="center">
  <img src="assets/clawdiney-image.jpeg" alt="Clawdiney Banner" width="100%">
</p>

---

## 🚀 Overview

Clawdiney is a **multi-vault** knowledge system. It indexes multiple Obsidian vaults — one per project — and provides semantic search + knowledge graph navigation for AI agents.

Core capabilities:

- **Multi-Vault Architecture:** Each project gets its own vault with isolated data (separate ChromaDB collection, namespaced Neo4j nodes)
- **CWD Auto-Detection:** The system detects which vault to use based on your current working directory — no manual switching
- **Semantic Search:** Finds patterns, SOPs and components by meaning (not just keywords)
- **Knowledge Graph:** Maps relationships between notes via `[[WikiLinks]]`  
- **Linking & Fallback:** Vaults can link to related vaults (e.g., SDK projects link to their parent project). Searches cascade through the chain: current vault → linked vaults → general
- **Native Integration:** Connects to MCP-compatible agents (OpenCode, Claude Code, etc.) via SSE or stdio

---

## 📋 Prerequisites

Before starting, make sure you have installed:

| Software | Minimum Version | Link |
|----------|-----------------|------|
| **Docker** | 20.x+ | [docker.com](https://docs.docker.com/get-docker/) |
| **Docker Compose** | 2.x+ | Included in Docker Desktop or `apt install docker-compose-plugin` |
| **Ollama** | 0.1.x+ | [ollama.com](https://ollama.com/) |
| **Python** | 3.10+ | Usually already installed on Unix systems. If not: `apt install python3` or `brew install python@3.12` |

**Supported Systems:**
- ✅ Linux (Ubuntu, Debian, Fedora, Arch, etc.)
- ✅ macOS (Intel and Apple Silicon)
- ✅ WSL2 (Windows Subsystem for Linux)
- ✅ BSD (FreeBSD, OpenBSD - with manual adjustments)

---

## 🛠️ Quick Installation

**Clone this repository:**
```bash
git clone git@github.com:elaranjo/clawdiney.git
cd clawdiney
```

**Configure `.env`:**
```bash
cp .env.example .env
nano .env
```

**Run the Bootstrapper:**
```bash
chmod +x scripts/setup_brain.sh
./scripts/setup_brain.sh
```

---

## 📋 What the Bootstrapper Does

The `setup_brain.sh` script automatically executes:

| Step | Action |
|------|--------|
| 🔍 | Checks if Docker, Docker Compose and Ollama are installed |
| 📝 | Creates `.env` with default settings (if it doesn't exist) |
| 🐳 | Starts Neo4j + ChromaDB containers via Docker Compose |
| 🐍 | Creates Python virtual environment (`venv`) |
| 📦 | Installs Python dependencies (`neo4j`, `chromadb`, `ollama`, etc.) |
| ✅ | **Checks and auto-repairs** missing dependencies |
| 🦙 | Downloads embedding model (`bge-m3`) via Ollama |
| 🧠 | Indexes your vault(s) in the database |

---

## 🏗️ Multi-Vault Architecture

### How Vaults Work

Clawdiney discovers vaults by scanning subdirectories in `VAULTS_DIR` (default: `~/clawdiney-vaults/`). Each subdirectory must contain a `clawdiney.toml` config file.

### clawdiney.toml format

Each vault requires a minimal config file:

```toml
id = "Budget"
name = "Budget"
description = "Projeto: Budget"
linked_vaults = ["general"]
```

| Field | Description |
|-------|-------------|
| `id` | Unique vault identifier (matched against directory names for CWD detection) |
| `name` | Display name |
| `description` | Optional description |
| `linked_vaults` | Vault IDs for fallback search (e.g., SDK → parent project) |

### CWD Auto-Detection (Convention > Configuration)

When you call any MCP tool without specifying `vault=`, Clawdiney inspects your current working directory. It walks the path **backwards** until it finds a directory name matching a vault `id`.

| Your CWD | Detected Vault |
|---|---|
| `~/projetos/Budget/` | `Budget` |
| `~/projetos/OnflyApi/src/` | `OnflyApi` |
| `~/projetos/Budget-SDK/` | `Budget-SDK` |
| `/any/other/directory` | `general` (fallback) |

### Linking & Fallback Chain

Vaults can link to related vaults for broader search results:

```
Budget-SDK ──linked_to──► [general, Budget]
                                │
User-SDK  ──linked_to──► [general, User]
                                │
clawdiney ──linked_to──► []   (isolated — no fallback)
```

When searching, Clawdiney queries: **current vault → linked vaults (in order) → general**. Results from all sources are merged and deduplicated.

### Using Your Personal Vault as `general`

To make your personal Obsidian vault the fallback `general` vault, create a symlink:

```bash
# Create clawdiney.toml inside your personal vault
cat >> /path/to/ObsidianVault/clawdiney.toml << 'EOF'
id = "general"
name = "General"
description = "Personal Obsidian vault - general knowledge"
linked_vaults = []
EOF

# Create symlink
ln -sfn /path/to/ObsidianVault ~/clawdiney-vaults/general

# Reindex
OLLAMA_HOST= ./venv/bin/python3 -m clawdiney.indexer
```

### Provisioning Project Vaults

For teams with multiple projects, use the provisioning script to scan a projects directory and create vaults automatically:

```bash
./scripts/provision_project_vaults.sh
```

This scans `~/projetos/` and creates a vault per project with:
- Auto-generated `clawdiney.toml` (SDKs linked to parent, clawdiney isolated)
- P.A.R.A. folder structure (`00_Inbox`, `10_Projects`, `20_Areas`, `30_Resources`, `40_Archives`, `50_Daily`)
- Project analysis files (README, Architecture, API docs, Domain model)

---

## 🔌 MCP Client Configuration

### Option A: Docker (SSE — Recommended)

The Docker container uses SSE transport on port 8006:

```json
{
  "projects": {
    "/path/to/your/project": {
      "mcpServers": {
        "clawdiney": {
          "url": "http://localhost:8006/mcp"
        }
      }
    }
  }
}
```

### Option B: Local Python (stdio)

```json
{
  "projects": {
    "/home/YOUR_PROJECTS_DIR": {
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

> **Note:** The Docker container uses SSE transport. The local Python server defaults to stdio. Set `MCP_TRANSPORT=sse` in your `.env` for local SSE mode.

For detailed Docker deployment instructions, see [DOCKER_MCP.md](DOCKER_MCP.md).

---

## 🚀 Usage

### Start All Services

To start all services (Neo4j, ChromaDB and MCP Server) together:

```bash
./scripts/run_brain.sh
```

This script will:
- Start Docker containers for Neo4j and ChromaDB
- Wait for services to initialize
- Index the Obsidian vault
- Start the MCP server in background

### Stop All Services

To stop all services, press Ctrl+C in the terminal where `run_brain.sh` is running, or execute:

```bash
docker compose -f docker/docker-compose.yml down
```

### Via MCP Client (Recommended)

With MCP configured, the agent has access to **read and write** tools:

#### Read Tools (Discovery)

- `search_brain(query)` - Search for architectural patterns, SOPs, and design system components
- `explore_graph(note_name)` - Find notes related to a specific topic via WikiLinks
- `resolve_note(name)` - Resolve ambiguous note names into canonical vault-relative paths
- `get_note_chunks(path)` - Inspect indexed chunk headers for a resolved note
- `health_check()` - Check health status of ChromaDB, Neo4j, and Ollama

#### Write Tools (Knowledge Capture)

- `write_note(path, content, mode)` - Create or update a note at any vault location
- `append_to_daily(content)` - Append content to today's daily note (50_Daily/YYYY-MM-DD.md)
- `add_learning(topic, content, area)` - Save learnings to appropriate folder (SOPs, Architecture, etc.)
- `delete_note(path)` - Delete a note and remove from index

**Example Workflow:**

> *"Check in the Brain if there are any SOPs for production deployment."*
> → Found existing SOP, update it: `write_note("30_Resources/SOPs/SOP_Deploy.md", updated_content, mode="overwrite")`

> *"Search the brain for UI Design System patterns."*
> → No pattern found, create new: `add_learning("Button_Component", "# Design System\\n\\nButton patterns...", area="DesignSystem")`

> *"Document today's learnings about the project."*
> → `append_to_daily("## Learnings\\n- Discovered X about the architecture")`

Full-file reading is intentionally outside the MCP workflow. The agent should use the repository or vault filesystem directly after `search_brain` has identified the relevant note.

### Via Shell (Alternative)

If MCP is not available, use the direct script:

```bash
./scripts/ask_brain.sh "production deployment patterns"
```

### Via Python (For developers)

```bash
./venv/bin/python3 -m clawdiney.query_engine "your query here"
```

---

## 🧩 Architecture

```
┌─────────────────────────────────────────────────────────┐
│                AI Agent (OpenCode, Claude, etc.)        │
└────────────────────────┬────────────────────────────────┘
                         │ MCP Protocol (SSE / stdio)
                         ▼
┌─────────────────────────────────────────────────────────┐
│              Clawdiney MCP Server                        │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────┐ │
│  │  ChromaDB    │ │    Neo4j     │ │  Vault Detector  │ │
│  │  (Vector)    │ │   (Graph)    │ │  (CWD-based)     │ │
│  │  per-vault   │ │  namespaced  │ │  → vault_id      │ │
│  │  collections │ │  :Note nodes │ └──────────────────┘ │
│  └──────┬───────┘ └──────┬───────┘                      │
└─────────┼────────────────┼──────────────────────────────┘
          │                │
          ▼                ▼
┌─────────────────────────────────────────────────────────┐
│              VAULTS_DIR (~/clawdiney-vaults/)            │
│                                                         │
│  Budget/  Budget-SDK/  OnflyApi/  User/  channel-back/  │
│  Company/ Company-SDK/ credit/    ...→ general/ (symlink)│
│                                                         │
│  Each vault has: clawdiney.toml + P.A.R.A. structure    │
└─────────────────────────────────────────────────────────┘
```

## 📁 Project Structure

```
clawdiney/
├── src/clawdiney/            # Main Python package
│   ├── __init__.py           # Package exports
│   ├── config.py             # Multi-vault configuration with VAULTS_DIR discovery
│   ├── vault_config.py       # VaultConfig dataclass + clawdiney.toml parser
│   ├── indexer.py            # Full indexing (ChromaDB per-vault + Neo4j namespaced)
│   ├── incremental_indexer.py# Incremental sync with state tracking
│   ├── query_engine.py       # Hybrid search with vault fallback chain
│   ├── vault_writer.py       # Thread-safe write operations per vault
│   ├── mcp_server.py         # MCP server with CWD auto-detection + vault parameter
│   ├── mcp_wrapper.py        # Docker MCP wrapper (SSE transport)
│   ├── chunking.py           # Text chunking strategies
│   ├── constants.py          # Application constants
│   ├── embedding_providers.py# Embedding provider interfaces
│   ├── logging_config.py     # Logging setup
│   ├── cli.py                # CLI entry point
│   └── scripts/
│       ├── watch_vault.py    # File watcher for real-time sync
│       └── sync_vault.py     # Manual sync script (per-vault aware)
│
├── tests/                    # Test suite
│   ├── test_config.py
│   ├── test_vault_config.py
│   ├── test_indexer.py
│   ├── test_query_engine.py
│   ├── test_mcp_server.py
│   ├── test_vault_writer.py
│   └── ...
│
├── scripts/                  # Shell scripts
│   ├── setup_brain.sh        # Bootstrap setup
│   ├── run_brain.sh          # Start all services
│   ├── ask_brain.sh          # Query from command line
│   ├── run_tests.sh          # Run test suite
│   ├── provision_project_vaults.sh  # Scan ~/projetos/ and create vaults
│   ├── migrate_to_multi_vault.sh    # Migrate single-vault to multi-vault
│   └── ...
│
├── docker/                   # Docker configuration
│   ├── Dockerfile
│   └── docker-compose.yml
│
├── .env.example              # Environment template with multi-vault setup
├── pyproject.toml             # Python project configuration
├── requirements.txt           # Python dependencies
└── README.md                  # This file
```

---

## 🔄 Updating Knowledge

**Good news:** Clawdiney now has **automatic sync**! No need to manually re-index.

### Auto-Sync (Default)
The MCP server automatically checks for vault changes on startup and syncs any modified files.

### Real-Time Watcher (Optional)
For active development, run the file watcher that syncs changes in real-time:

```bash
# Continuous watcher mode
WATCHER_MODE=true ./scripts/run_brain.sh

# Or directly
./venv/bin/python3 -m clawdiney.scripts.watch_vault
```

### Manual Sync (On-Demand)
```bash
# Check sync status
./venv/bin/python3 -m clawdiney.scripts.sync_vault --status

# Incremental sync (only changed files)
./venv/bin/python3 -m clawdiney.scripts.sync_vault

# Full sync (reindex everything)
./venv/bin/python3 -m clawdiney.scripts.sync_vault --full
```

The agent has immediate access to new/modified notes after sync completes.

---

## 🛡️ Privacy and Security

- **Multi-Vault Isolation:** Each project's data stays in its own directory under `VAULTS_DIR`. No vault reads another vault's `.md` files.
- **Symlink Support:** You can symlink a vault directory, allowing you to keep your personal vault in one location while Clawdiney references it.
- **Local Data:** Everything runs locally on your machine. Nothing is sent to the cloud (except if you use cloud models).
- **Isolation:** Database data (Neo4j/ChromaDB) stays in local Docker volumes.

---

## 🐛 Troubleshooting

### MCP client doesn't see the server
- Check if the client configuration points to `clawdiney.mcp_server` or `http://localhost:8006/mcp`.
- Restart the client session.
- Test the server manually: `./venv/bin/python3 -m clawdiney.mcp_server` (stdio) or `curl http://localhost:8006/sse` (SSE)

### Neo4j connection error / Container restarting
- Check if the container is running: `docker compose -f docker/docker-compose.yml ps neo4j`
- If `neo4j_data/` has permission issues (UID 7474 ownership): `sudo chown -R 7474:7474 neo4j_data && docker compose restart neo4j`
- If the problem persists, delete the data: `sudo rm -rf neo4j_data && docker compose restart neo4j`

### ChromaDB connection error
- Check logs: `docker compose -f docker/docker-compose.yml logs chromadb`
- Recreate the database (data will be lost): `rm -rf chroma_data && docker compose -f docker/docker-compose.yml up -d`

### MCP Server restart loop (Docker)
- The Docker container now uses **SSE transport** (fixed in v2.0). If you see continuous restarts:
  - Verify `MCP_TRANSPORT=sse` in `docker/docker-compose.yml`
  - Verify `OLLAMA_HOST=host.docker.internal` is set for container-to-host Ollama connectivity
  - Check logs: `docker compose -f docker/docker-compose.yml logs mcp-server`

---

## 📚 Useful Commands

```bash
# Check container status
docker compose ps

# View Neo4j logs
docker compose logs neo4j

# Stop all services
docker compose down

# Start all services (including MCP Server)
./run_brain.sh

# Start with file watcher (real-time sync)
WATCHER_MODE=true ./run_brain.sh

# Check sync status
./venv/bin/python3 sync_vault.py --status

# Incremental sync (only changed files)
./venv/bin/python3 sync_vault.py

# Full sync (reindex everything)
./venv/bin/python3 sync_vault.py --full

# Test search
./ask_brain.sh "your query"
```

---

## ❓ FAQ (Frequently Asked Questions)

### "Do I need Obsidian installed?"
**No.** Obsidian is just an editor. The Brain reads `.md` files directly, so you only need the Vault files.

### "Can I use my personal vault?"
**Yes!** Use the symlink approach:
```bash
# Add clawdiney.toml to your personal vault
cat >> /path/to/your/vault/clawdiney.toml << 'EOF'
id = "general"
name = "General"
description = "Personal Obsidian vault"
linked_vaults = []
EOF

# Symlink it as the general vault
ln -sfn /path/to/your/vault ~/clawdiney-vaults/general

# Reindex
./venv/bin/python3 -m clawdiney.indexer
```
Your vault becomes the fallback `general` vault — searched whenever a more specific vault doesn't match.

### "How long does indexing take?"
Initial full sync depends on vault size:
- **Small vault** (< 100 notes): ~30 seconds
- **Medium vault** (100-500 notes): 1-2 minutes
- **Large vault** (> 500 notes): 3-5 minutes

**Incremental sync** (subsequent syncs) only processes changed files and is much faster (typically 1-5 seconds per file).

### "Do I need to re-index every time I update an SOP?"
**No!** Auto-sync handles this automatically:
- **On MCP startup:** Checks for changes and syncs automatically
- **With Watcher mode:** Syncs in real-time as you edit files
- **Manual:** Run `python sync_vault.py` for on-demand sync

### "Does it work on Windows?"
**Yes!** Through **WSL2** (Windows Subsystem for Linux). Follow these steps:
1. Install WSL2: `wsl --install` (in PowerShell as Admin)
2. Install Docker Desktop for Windows and enable WSL2 integration
3. Inside WSL2, follow the normal installation instructions as if it were Linux

### "Which Linux distribution is recommended?"
The system has been tested mainly on **Ubuntu 22.04+** and **Debian 11+**, but it should work on any modern distribution with Docker and Python 3.10+.

### "What if I use another model instead of Qwen in Ollama?"
**It works normally.** The Brain is model-agnostic. You use whatever model you prefer in Claude Code. The `bge-m3` is just for generating embeddings (vectors), not for answering questions.

### "Can the agent write new notes automatically?"
**Yes!** The MCP server includes write tools:
- `write_note(path, content)` - Create or update any note
- `append_to_daily(content)` - Add to today's daily note
- `add_learning(topic, content, area)` - Save learnings to the right folder

When the agent learns something new during a task, it can save it directly to the vault. The change is automatically indexed and becomes searchable within seconds.

### "Where should I save different types of content?"
Use the `add_learning()` tool which automatically routes to the correct folder:

| Area | Folder | Example |
|------|--------|---------|
| `SOPs` | `30_Resources/SOPs/` | Procedures and standards |
| `Architecture` | `30_Resources/Architecture/` | ADRs and design decisions |
| `DesignSystem` | `30_Resources/DesignSystem/` | UI components and patterns |
| `Projects` | `10_Projects/` | Active project documentation |
| `Areas` | `20_Areas/` | Ongoing responsibility areas |
| `Learnings` | `30_Resources/Learnings/` | General insights |

---

## 🤝 Contributing

To add new tools to MCP:
1. Edit `brain_mcp_server.py`
2. Add a new function decorated with `@mcp.tool()`
3. Test locally before committing.

---

## 📄 License

MIT License

---

**Created with ❤️ by the Voices in My Head team**

**Compatibility:** Linux • macOS • WSL2 • Unix-like
