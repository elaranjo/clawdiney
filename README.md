# 🧠 Clawdiney

**Hybrid Vector + Graph Knowledge System for AI Coding Agents**

Clawdiney transforms your Obsidian Vault into a living knowledge source for AI coding agents like Claude Code. It enables semantic search and knowledge graph navigation of company SOPs, design systems, architectural patterns, and documentation.

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose
- Python 3.10+
- Ollama (https://ollama.com/)

### Installation
```bash
# Clone the repository
git clone https://github.com/elaranjo/clawdiney.git
cd clawdiney

# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy and configure environment variables
cp .env.example .env
# Edit .env with your configuration
```

### Usage
```bash
# Start all services
./run_brain.sh

# Or start infrastructure manually
docker-compose up -d

# Index your Obsidian vault
python brain_indexer.py

# Start MCP server
python brain_mcp_server.py
```

## 📚 Features

- **Semantic Search**: Find patterns, SOPs, and components by meaning
- **Knowledge Graph**: Map relationships between notes via `[[WikiLinks]]`
- **MCP Integration**: Native Claude Code integration via Model Context Protocol
- **Vector Database**: Powered by ChromaDB for embeddings
- **Graph Database**: Neo4j for relationship mapping

## 🔧 Configuration

See `.env.example` for all configuration options.

## 🛡️ Privacy & Security

- **Local Data**: Everything runs locally on your machine
- **No Cloud Upload**: Data stays on your computer (except for Ollama models)
- **Isolated Storage**: Database data stored in local Docker volumes

## 🤝 Contributing

Contributions welcome! Please read our contributing guidelines.

## 📄 License

MIT License - See LICENSE file for details.
