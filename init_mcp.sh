#!/bin/bash
# Script para inicializar o servidor MCP do Clawdiney.
# Aguarda dependências, indexa o vault e depois inicia o servidor MCP.

set -eu

echo "🔧 Iniciando processo de inicialização do MCP Server..."

# Verificar se o vault existe
VAULT_PATH="${VAULT_PATH:-/vault}"
if [ ! -d "$VAULT_PATH" ]; then
    echo "⚠️  Caminho do Vault não encontrado: $VAULT_PATH"
    echo "   Certifique-se de montar o volume do vault corretamente."
    exit 1
fi

# Contar arquivos no vault
FILE_COUNT=$(find "$VAULT_PATH" -name "*.md" | wc -l)
echo "📄 Encontrados $FILE_COUNT arquivos Markdown no vault"

if [ "$FILE_COUNT" -eq 0 ]; then
    echo "⚠️  Nenhum arquivo .md encontrado no vault. Continuando mesmo assim..."
fi

wait_for_tcp() {
    local host="$1"
    local port="$2"
    local label="$3"

    echo "⏳ Aguardando $label em $host:$port ..."
    python - "$host" "$port" "$label" <<'PY'
import socket
import sys
import time

host, port, label = sys.argv[1], int(sys.argv[2]), sys.argv[3]
deadline = time.time() + 60
last_error = None

while time.time() < deadline:
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"✅ {label} disponível em {host}:{port}")
            sys.exit(0)
    except OSError as exc:
        last_error = exc
        time.sleep(2)

print(f"❌ Timeout aguardando {label}: {last_error}", file=sys.stderr)
sys.exit(1)
PY
}

wait_for_tcp "${CHROMA_HOST:-chromadb}" "${CHROMA_PORT:-8000}" "ChromaDB"

NEO4J_TARGET="${NEO4J_URI:-bolt://neo4j:7687}"
NEO4J_TARGET="${NEO4J_TARGET#*://}"
NEO4J_HOST="${NEO4J_TARGET%%:*}"
NEO4J_PORT="${NEO4J_TARGET##*:}"
wait_for_tcp "${NEO4J_HOST}" "${NEO4J_PORT}" "Neo4j"

# Verificar modo de operação
WATCHER_MODE="${WATCHER_MODE:-false}"

if [ "$WATCHER_MODE" = "true" ]; then
    echo "🔍 Iniciando file watcher com auto-sync..."
    exec python /app/watch_vault.py
else
    # Indexação inicial é feita pelo MCP server (auto-sync)
    echo "ℹ️  Indexação inicial será feita pelo MCP server (auto-sync)"
    echo "💡 Dica: Use WATCHER_MODE=true para rodar o file watcher contínuo"
    echo ""
    echo "🚀 Iniciando servidor MCP..."
    exec python /app/mcp_wrapper.py
fi
