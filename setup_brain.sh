#!/bin/bash
# Clawdiney - Setup Bootstrapper
# This script automates the entire setup process for new team members

set -e  # Exit on error

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Clawdiney - Setup Bootstrapper"
echo "=================================="
echo ""

# 1. Check if Docker is installed
echo "🔍 Checking Docker..."
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first: https://docs.docker.com/get-docker/"
    exit 1
fi
echo "✅ Docker found"

# 2. Check if Docker Compose is available
echo "🔍 Checking Docker Compose..."
if ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose is not installed. Please install it first."
    exit 1
fi
echo "✅ Docker Compose found"

# 3. Check if Ollama is installed
echo "🔍 Checking Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama is not installed. Please install Ollama first: https://ollama.com/"
    exit 1
fi
echo "✅ Ollama found"

# 4. Create .env file if it doesn't exist
echo ""
echo "📝 Checking configuration (.env)..."
if [ ! -f ".env" ]; then
    echo "⚠️  .env file not found. Creating from .env.example..."
    cp .env.example .env
    echo "✅ .env created. Please edit it to match your setup (VAULT_PATH, etc.)"
    echo "   Press Enter after editing, or Ctrl+C to cancel and edit manually..."
    read -p ""
else
    echo "✅ .env found"
fi

# 5. Start Docker containers (Neo4j + ChromaDB)
echo ""
echo "🐳 Starting Docker containers (Neo4j + ChromaDB)..."
docker compose up -d
echo "✅ Containers started"

# 6. Wait for Neo4j to be ready
echo ""
echo "⏳ Waiting for Neo4j to be ready..."
sleep 10
echo "✅ Neo4j should be ready"

# 7. Create Python virtual environment
echo ""
echo "🐍 Setting up Python virtual environment..."
if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "✅ Virtual environment already exists"
fi

# 8. Install Python dependencies
echo ""
echo "📦 Installing Python dependencies..."
"$SCRIPT_DIR/venv/bin/pip" install --upgrade pip > /dev/null 2>&1
"$SCRIPT_DIR/venv/bin/pip" install -r requirements.txt
echo "✅ Dependencies installed"

# 8.5. Verify installation
echo ""
echo "🔍 Verifying Python dependencies..."
if ! "$SCRIPT_DIR/venv/bin/python3" -c "import neo4j, chromadb, ollama, dotenv" 2>/dev/null; then
    echo "⚠️  Some dependencies are missing. Reinstalling..."
    "$SCRIPT_DIR/venv/bin/pip" install -r requirements.txt --force-reinstall
    echo "✅ Dependencies reinstalled"
else
    echo "✅ All dependencies verified"
fi

# 9. Pull the embedding model via Ollama
echo ""
echo "🦙 Pulling embedding model (bge-m3) via Ollama..."
ollama pull bge-m3
echo "✅ Model ready"

# 10. Run the indexer to populate the databases
echo ""
echo "🧠 Indexing your Obsidian Vault..."
echo "   This may take a few minutes depending on the size of your vault..."
"$SCRIPT_DIR/venv/bin/python3" "$SCRIPT_DIR/brain_indexer.py"
echo "✅ Vault indexed!"

# 11. Configure Claude Code (Optional)
echo ""
echo "🤖 Configuring Claude Code MCP integration..."
read -p "Do you want to automatically configure Claude Code? (y/n): " configure_claude
if [[ $configure_claude =~ ^[Yy]$ ]]; then
    CLAUDE_CONFIG="$HOME/.claude.json"
    
    if [ -f "$CLAUDE_CONFIG" ]; then
        echo "⚠️  Found existing Claude config at $CLAUDE_CONFIG"
        echo "   The MCP server configuration will be added to the 'projetos' project entry."
        echo "   Press Enter to continue, or Ctrl+C to skip..."
        read -p ""
        
        # Note: This is a simplified approach. A full implementation would use jq to properly merge JSON.
        echo "✅ Claude Code configuration note: Please ensure the MCP server is added to your .claude.json"
        echo "   See the README.md for manual configuration instructions."
    else
        echo "⚠️  Claude Code config not found at $CLAUDE_CONFIG"
        echo "   Run Claude Code once to generate the config, then re-run this script or configure manually."
    fi
fi

echo ""
echo "======================================"
echo "🎉 Clawdiney Setup Complete!"
echo "======================================"
echo ""
echo "Next steps:"
echo "1. Make sure your Obsidian Vault path in .env is correct"
echo "2. Start Claude Code in your projects folder: ollama launch claude --model qwen3-next:80b-cloud"
echo "3. Test the integration by asking: 'Search the brain for backend repository standards'"
echo ""
echo "📚 For more information, see README.md"
echo ""
