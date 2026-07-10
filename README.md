# 🧠 Clawdiney

[![CI](https://github.com/elaranjo/clawdiney/actions/workflows/ci.yml/badge.svg)](https://github.com/elaranjo/clawdiney/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/clawdiney.svg)](https://pypi.org/project/clawdiney/)
[![Python Version](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue.svg)](https://github.com/elaranjo/clawdiney)
[![Coverage](https://img.shields.io/badge/coverage-59%25-green.svg)](https://github.com/elaranjo/clawdiney)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Expanded Brain for Coding Agents**

A hybrid **Vector + Graph** system that transforms your Obsidian vaults into a living knowledge source for AI coding agents.

<p align="center">
  <img src="assets/clawdiney-image.jpeg" alt="Clawdiney Banner" width="100%">
</p>

---

## 🚀 Overview

Clawdiney is a **multi-vault** knowledge system. It indexes multiple Obsidian vaults — one per project — and provides semantic search + knowledge graph navigation for AI agents.

Core capabilities:

- **Zero-infrastructure storage (v0.2.0):** Everything lives in a single local SQLite file (`brain.db`) — vectors via `sqlite-vec`, full-text via FTS5, knowledge graph via relational tables. **No Docker, no Neo4j, no ChromaDB, no Redis.**
- **Hybrid Search:** BM25 (exact terms, acronyms, identifiers) + semantic vectors, fused with Reciprocal Rank Fusion; optional cross-encoder reranking (`pip install clawdiney[rerank]`)
- **Multi-Vault Architecture:** Each project gets its own vault with isolated data (vault-scoped rows in the same database)
- **CWD Auto-Detection:** The system detects which vault to use based on your current working directory — no manual switching
- **Knowledge Graph:** Maps relationships between notes via `[[WikiLinks]]` and shared tags
- **Linking & Fallback:** Vaults can link to related vaults (e.g., SDK projects link to their parent project). Searches cascade through the chain: current vault → linked vaults → general
- **Native Integration:** Connects to MCP-compatible agents (OpenCode, Claude Code, etc.) via SSE or stdio
- **Agent-Written Memory:** `write_memory` turns conversational facts into provenance-marked, searchable notes — resolved against existing entities, deduped, and optionally namespaced per agent (`agent_id`)
- **Bi-Temporal Facts & Conflict Detection:** Graph facts carry validity windows; when an LLM-extracted fact genuinely changes value, both versions are kept and flagged rather than one silently overwriting the other
- **Measured, Not Assumed:** `clawdiney-eval` scores retrieval quality (recall@k/MRR/hit-rate) per mode against a regression baseline — see [`BENCHMARKS.md`](BENCHMARKS.md)

> **Migrating from v0.1.x (Docker stack)?** The Neo4j/ChromaDB/Redis containers are no longer used. Just install v0.2.0, keep Ollama running, and run `clawdiney-index` once to rebuild the index into `brain.db`. Your vault files are the source of truth — nothing is lost. Old Docker volumes can be removed with `docker compose -f docker/docker-compose.yml down -v`.

---

## ⚖️ Why Embedded SQLite Instead of a Service Stack

Peers in the AI-agent-memory space (mem0, Zep/Graphiti, Letta/MemGPT) typically run a vector DB + graph DB + cache as separate services. Clawdiney holds vectors (`sqlite-vec`), full-text (FTS5), and the knowledge graph in one `brain.db` file:

| | Clawdiney | Typical peer stack |
|---|---|---|
| Infrastructure | 1 file (`brain.db`) | Vector DB + graph DB (e.g. Neo4j) + cache (e.g. Redis) |
| Setup | `pip install`, point `BRAIN_DB_PATH` | Provision + configure 2-3 services |
| Deploy | Copy a file | Orchestrate a stack (Docker Compose / k8s) |
| Backup | Copy a file | Backup each service independently |

This is a deliberate trade-off: embedded SQLite means single-writer-at-a-time semantics and no built-in horizontal scaling — right for a single-user or small-team coding-agent memory layer, not a multi-tenant SaaS backend. See [`BENCHMARKS.md`](BENCHMARKS.md) for retrieval-quality numbers (recall@k/MRR/hit-rate by mode) and reranker latency/precision trade-offs, measured with the built-in eval harness (`clawdiney-eval`).

---

## 📋 Prerequisites

Before starting, make sure you have installed:

| Software | Minimum Version | Link |
|----------|-----------------|------|
| **Ollama** | 0.3.x+ | [ollama.com](https://ollama.com/) (embedding model `bge-m3`) |
| **Python** | 3.10+ | Usually already installed on Unix systems. If not: `apt install python3` or `brew install python@3.12` |

Optional:

| Extra | Install | What it adds |
|-------|---------|--------------|
| **Reranker** | `pip install clawdiney[rerank]` | Cross-encoder reranking (`BAAI/bge-reranker-v2-m3`, ~2GB RAM). Without it, searches use RRF ordering — still fully functional. |

**Configuration:** `BRAIN_DB_PATH` env var sets the database location (default: `~/.clawdiney/brain.db`). For the project knowledge graph: `CARD_LLM_MODEL` (Ollama model for project card Purpose/Architecture sections, default `qwen3`) and `ENTITY_RESOLUTION_THRESHOLD` (similarity cutoff for merging duplicate entities, default `0.85`).

**Cross-project intelligence:** the project indexer builds a typed knowledge graph (dependencies, shared datastores, patterns) from your codebases. Agents can call `get_project_card("name")` for a project overview and `how_do_projects_relate("a", "b")` to see how two projects connect, with evidence.

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
| 🔍 | Checks if Ollama is installed |
| 📝 | Creates `.env` with default settings (if it doesn't exist) |
| 🐍 | Creates Python virtual environment (`venv`) |
| 📦 | Installs Python dependencies (`sqlite-vec`, `ollama`, `mcp`, etc.) |
| 🦙 | Downloads embedding model (`bge-m3`) via Ollama |
| 🧠 | Indexes your vault(s) into `brain.db` |

---

## 🏗️ Multi-Vault Architecture

### How Vaults Work

Clawdiney discovers vaults by scanning subdirectories in `VAULTS_DIR` (default: `~/clawdiney-vaults/`). Each subdirectory must contain a `clawdiney.toml` config file.

### clawdiney.toml format

Each vault requires a minimal config file:

```toml
id = "Payments"
name = "Payments"
description = "Payments service"
linked_vaults = ["general"]
```

| Field | Description |
|-------|-------------|
| `id` | Unique vault identifier (matched against directory names for CWD detection) |
| `name` | Display name |
| `description` | Optional description |
| `linked_vaults` | Vault IDs for fallback search (e.g., a client SDK linked to the service it wraps) |

### CWD Auto-Detection (Convention > Configuration)

When you call any MCP tool without specifying `vault=`, Clawdiney inspects your current working directory. It walks the path **backwards** until it finds a directory name matching a vault `id`.

| Your CWD | Detected Vault |
|---|---|
| `~/projetos/Payments/` | `Payments` |
| `~/projetos/MyCompanyApi/src/` | `MyCompanyApi` |
| `~/projetos/Payments-SDK/` | `Payments-SDK` |
| `/any/other/directory` | `general` (fallback) |

### Linking & Fallback Chain

Vaults can link to related vaults for broader search results:

```
Payments-SDK ──linked_to──► [general, Payments]
                                  │
Auth-SDK     ──linked_to──► [general, Auth]
                                  │
clawdiney    ──linked_to──► []   (isolated — no fallback)
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

Clawdiney runs as a local Python process (stdio transport) — no server to start separately, no container. Your MCP client (Claude Code, OpenCode, etc.) launches it on demand.

**Claude Code** (`~/.claude.json`, project scope):
```json
{
  "projects": {
    "/home/YOUR_PROJECTS_DIR": {
      "mcpServers": {
        "clawdiney": {
          "command": "/path/to/clawdiney/venv/bin/python3",
          "args": ["-m", "clawdiney.mcp_server"],
          "env": {
            "VAULTS_DIR": "/path/to/your/vaults",
            "MCP_DEFAULT_VAULT": "general",
            "MODEL_NAME": "bge-m3:latest",
            "ENABLE_RERANK": "true"
          }
        }
      }
    }
  }
}
```

**OpenCode** (`opencode.json`):
```json
{
  "mcp": {
    "clawdiney": {
      "type": "local",
      "command": ["/path/to/clawdiney/venv/bin/python3", "-m", "clawdiney.mcp_server"],
      "enabled": true,
      "environment": {
        "VAULTS_DIR": "/path/to/your/vaults",
        "MCP_DEFAULT_VAULT": "general",
        "MODEL_NAME": "bge-m3:latest",
        "ENABLE_RERANK": "true"
      }
    }
  }
}
```

Restart the client session after registering — MCP config is read once at session start.

> Remote/network access (SSE transport) is still available by setting `MCP_TRANSPORT=sse` before launching `clawdiney.mcp_server` directly, but stdio (the default, no config needed) is what both clients above use and is the supported path.

---

## 🚀 Usage

### Ensure Ollama Is Running

Clawdiney's only external dependency is Ollama (for embeddings, and card-generation LLM calls). Everything else — vectors, full-text search, and the knowledge graph — lives in a single embedded SQLite file (`brain.db`, default `~/.clawdiney/brain.db`). No services to start or stop.

```bash
ollama serve   # if not already running as a daemon
ollama pull bge-m3
```

### Index Your Vault(s)

```bash
./venv/bin/python3 -m clawdiney.indexer
```

### Via MCP Client (Recommended)

With MCP configured, the agent has access to **read and write** tools:

#### Read Tools (Discovery)

- `search_brain(query, vault?, agent_id?)` - Hybrid search (BM25 + vector, RRF-fused, optionally reranked) for architectural patterns, SOPs, and design system components. `agent_id` (optional) also searches that agent's own memory (see `write_memory` below) alongside shared vault content; results append an "Unresolved conflicts" section when a returned note touches a contradicted fact
- `explore_graph(note_name, vault?, agent_id?)` - Find entities related to a note or project — notes, WikiLinks, tags, or (for projects) dependencies/patterns — with relation type and evidence. Same `agent_id` scoping and conflict surfacing as `search_brain`
- `resolve_note(name)` - Resolve ambiguous note names into canonical vault-relative paths
- `get_note_chunks(path)` - Inspect indexed chunk headers for a resolved note
- `get_project_card(name)` - Full project card (Purpose, Stack, Architecture, Interfaces) — the first call when touching an unfamiliar project
- `how_do_projects_relate(a, b, vault?, agent_id="*")` - Graph paths between two projects (shared dependencies, datastores, patterns) with evidence. `agent_id="*"` (default) applies no filtering; pass a specific id to additionally restrict to that agent's own relations
- `health_check()` - Check health of `brain.db`, Ollama, and the optional reranker, plus per-vault document counts

#### Write Tools (Knowledge Capture)

- `write_note(path, content, mode)` - Create or update a note at any vault location
- `write_memory(fact, source, agent_id="default", vault?)` - Persist a natural-language fact (ideally `"<Subject> <verb> <value>"`, e.g. `"User prefers embedded SQLite over Docker-based stacks"`) as agent-written memory. Resolves the subject against existing entities and writes to a provenance-marked `40_Memory/` note — the only write tool triggered by conversational knowledge rather than an explicit save request
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

> *"Remember that I prefer embedded SQLite over Docker-based stacks for this kind of tool."*
> → `write_memory("User prefers embedded SQLite over Docker-based stacks", source="conversation")`

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
│                AI Agent (Claude Code, OpenCode, etc.)    │
└────────────────────────┬────────────────────────────────┘
                         │ MCP Protocol (stdio)
                         ▼
┌─────────────────────────────────────────────────────────┐
│              Clawdiney MCP Server                        │
│  ┌──────────────────────────────┐ ┌──────────────────┐  │
│  │      Hybrid Query Engine     │ │  Vault Detector  │  │
│  │  BM25 (FTS5) + Vector (KNN)  │ │  (CWD-based)     │  │
│  │  → RRF fusion → rerank       │ │  → vault_id      │  │
│  └───────────────┬──────────────┘ └──────────────────┘  │
└──────────────────┼───────────────────────────────────────┘
                    ▼
┌─────────────────────────────────────────────────────────┐
│         brain.db (single embedded SQLite file)           │
│  documents · chunks · chunk_vectors (sqlite-vec)          │
│  chunk_fts (FTS5) · entities · relations (graph)          │
└─────────────────────────────────────────────────────────┘
                    ▲
                    │ indexed from
┌─────────────────────────────────────────────────────────┐
│              VAULTS_DIR (~/clawdiney-vaults/)            │
│                                                         │
│  general/ (personal vault)   clawdiney/ (this project)  │
│  Each vault has: clawdiney.toml + P.A.R.A. structure    │
└─────────────────────────────────────────────────────────┘
```

Only external dependency: **Ollama** (embeddings + card-generation LLM calls). No Docker, no separate vector/graph/cache servers.

## 📁 Project Structure

```
clawdiney/
├── src/clawdiney/             # Main Python package
│   ├── __init__.py            # Package exports
│   ├── config.py              # Multi-vault configuration, VAULTS_DIR discovery, BRAIN_DB_PATH
│   ├── vault_config.py        # VaultConfig dataclass + clawdiney.toml parser
│   ├── storage.py             # Embedded brain.db gateway (sqlite-vec + FTS5 + graph tables)
│   ├── indexer.py             # Full indexing into brain.db
│   ├── incremental_indexer.py # Incremental sync (content hashes stored in brain.db)
│   ├── query_engine.py        # Hybrid search (BM25 + vector, RRF fusion) + vault fallback chain
│   ├── reranker.py            # Cross-encoder reranking (optional extra, GPU→CPU fallback)
│   ├── embedding_providers.py # EmbeddingProvider protocol (Ollama default, OpenAI optional)
│   ├── vault_writer.py        # Thread-safe write operations per vault
│   ├── mcp_server.py          # MCP server: CWD auto-detection, search/graph/write tools
│   ├── project_indexer.py     # Analyzes codebases → enriched project cards for Obsidian
│   ├── project_index_config.py# Selective file indexing patterns (include/exclude)
│   ├── entity_extractor.py    # Project knowledge graph: manifest parsing + LLM extraction
│   ├── chunking.py            # Text chunking strategies
│   ├── constants.py           # Application constants
│   ├── logging_config.py      # Logging setup
│   ├── cli.py                 # CLI entry point (vault create/list)
│   └── scripts/
│       ├── watch_vault.py     # File watcher for real-time vault sync
│       ├── sync_vault.py      # Manual sync script (per-vault aware)
│       ├── watch_projects.py  # File watcher for codebase → project card sync
│       └── index_projects.py  # CLI: index projects to Obsidian
│
├── tests/                     # Test suite (pytest, no service mocks — real tempfile SQLite)
│   ├── test_storage.py
│   ├── test_query_engine.py
│   ├── test_hybrid_search.py
│   ├── test_reranker.py
│   ├── test_entity_extractor.py
│   ├── test_mcp_server.py
│   └── ...
│
├── scripts/                   # Shell scripts
│   ├── setup_brain.sh         # Bootstrap setup (venv, deps, pull embedding model, index)
│   ├── ask_brain.sh           # Query from command line
│   ├── run_tests.sh           # Run test suite
│   ├── claude_hook_context.py # Optional Claude Code UserPromptSubmit hook (proactive context)
│   ├── provision_project_vaults.sh
│   └── ...
│
├── .env.example                # Environment template with multi-vault setup
├── pyproject.toml               # Python project configuration (source of truth for dependencies)
└── README.md                    # This file
```

---

## 🔄 Updating Knowledge

**Good news:** Clawdiney now has **automatic sync**! No need to manually re-index.

### Auto-Sync (Default)
The MCP server automatically checks for vault changes on startup and syncs any modified files.

### Real-Time Watcher (Optional)
For active development, run the file watcher that syncs changes in real-time:

```bash
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
- **Single-file storage:** All indexed data lives in one local SQLite file (`brain.db`), scoped by vault at the row level. Delete the file to wipe everything; copy it to back everything up.

---

## 🐛 Troubleshooting

Start with the MCP `health_check()` tool — it reports `brain.db` status (path, document/chunk/entity/relation counts), Ollama connectivity, and whether the reranker loaded, plus per-vault document counts.

### MCP client doesn't see the server
- Check the client config points `command`/`args` at `<venv>/bin/python3 -m clawdiney.mcp_server` and restart the client session (MCP config is only read at session start).
- Test the server manually: `./venv/bin/python3 -m clawdiney.mcp_server` (should print Ollama model validation, then wait on stdio — Ctrl+C to stop).

### `search_brain` returns nothing
- Run `health_check()` — if `documents: 0`, the vault hasn't been indexed yet: `./venv/bin/python3 -m clawdiney.indexer`.
- Check `VAULTS_DIR` / `VAULT_PATH` env vars match where your `.md` files actually live.

### "Re-index required" / `SchemaMismatchError`
- `brain.db` was created with a different embedding model or dimension than your current config. Delete the file (`rm ~/.clawdiney/brain.db`, or your `BRAIN_DB_PATH`) and re-run the indexer — it rebuilds from your vault files, nothing else is lost.

### Reranker doesn't activate
- Check it's installed: `pip install clawdiney[rerank]` (adds `sentence-transformers`, ~2GB with model weights).
- On small/shared GPUs, the reranker automatically retries on CPU if CUDA runs out of memory — check the logs for "retrying on CPU". If it still fails, set `ENABLE_RERANK=false` to skip it entirely; search still works via BM25+vector RRF fusion.

### Reranker configuration

`RERANK_MODEL` selects the cross-encoder (default `BAAI/bge-reranker-v2-m3`, ~568M params). Any `sentence-transformers`-compatible cross-encoder works — e.g. a smaller/faster one:

```bash
RERANK_MODEL=cross-encoder/ms-marco-MiniLM-L-6-v2
```

Measured with `clawdiney-eval --mode hybrid --rerank` against the fixture vault (CPU fallback, 8 queries, warm model):

| Model | Params | Wall time (8 queries) | recall@5 / MRR / hit_rate |
|---|---|---|---|
| `BAAI/bge-reranker-v2-m3` (default) | ~568M | ~80s (~10s/query) | 1.00 / 1.00 / 1.00 |
| `cross-encoder/ms-marco-MiniLM-L-6-v2` | ~22M | ~30s (~4s/query) | 1.00 / 1.00 / 1.00 |
| *(rerank disabled)* | — | fastest, RRF order only | run `--no-rerank` to measure on your own vault |

On this small fixture both models score identically, so the numbers only show the latency delta — they don't prove the smaller model preserves precision on a larger, harder vault. Before adopting a non-default `RERANK_MODEL`, re-run `clawdiney-eval --all-modes` against your own vault (or an expanded golden set) and compare against the current baseline (`tests/eval/baseline.json`) rather than trusting these numbers directly.

### Ollama connection error
- Confirm Ollama is running: `ollama list`. Start it with `ollama serve` if not.
- Confirm the embedding model is pulled: `ollama pull bge-m3`.

---

## 📚 Useful Commands

```bash
# Check brain.db health (documents/chunks/entities/relations, Ollama, reranker)
# via any MCP client, or directly:
./venv/bin/python3 -c "from clawdiney.storage import get_storage; print(get_storage().stats())"

# Index all configured vaults
./venv/bin/python3 -m clawdiney.indexer

# Check sync status
./venv/bin/python3 -m clawdiney.scripts.sync_vault --status

# Incremental sync (only changed files)
./venv/bin/python3 -m clawdiney.scripts.sync_vault

# Full sync (reindex everything)
./venv/bin/python3 -m clawdiney.scripts.sync_vault --full

# Real-time file watcher
./venv/bin/python3 -m clawdiney.scripts.watch_vault

# Test search from the command line
./scripts/ask_brain.sh "your query"
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
**Yes!** Through **WSL2** (Windows Subsystem for Linux):
1. Install WSL2: `wsl --install` (in PowerShell as Admin)
2. Install Ollama for Windows (or inside WSL2) — see [ollama.com](https://ollama.com/)
3. Inside WSL2, follow the normal installation instructions as if it were Linux

### "Which Linux distribution is recommended?"
The system has been tested mainly on **Ubuntu 22.04+** and **Debian 11+**, but it should work on any modern distribution with Python 3.10+ and Ollama — no other OS-level requirements.

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
1. Edit `src/clawdiney/mcp_server.py`
2. Add a new function decorated with `@mcp.tool()`
3. Add tests (`tests/test_mcp_server.py`) and run `./scripts/run_tests.sh` before committing.

---

## 📄 License

MIT License

---

**Created with ❤️ by the Voices in My Head team**

**Compatibility:** Linux • macOS • WSL2 • Unix-like
