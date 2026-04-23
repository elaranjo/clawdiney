#!/bin/bash
# Script para executar o Clawdiney com todos os serviços integrados

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "🚀 Iniciando Clawdiney..."

# 1. Iniciar a infraestrutura Docker (Neo4j e ChromaDB)
echo "🐳 Iniciando infraestrutura Docker..."
docker compose -f docker/docker-compose.yml up -d chromadb neo4j

# 2. Aguardar alguns segundos para os serviços iniciarem
echo "⏳ Aguardando inicialização dos serviços..."
sleep 10

# 3. Verificar se os serviços estão rodando
echo "🔍 Verificando status dos serviços..."
docker compose -f docker/docker-compose.yml ps

# 4. Indexar o vault (se necessário)
echo "🔍 Indexando o vault..."
./venv/bin/python3 -m clawdiney.indexer

# 5. Iniciar o servidor MCP em background
echo "🧠 Iniciando servidor Clawdiney..."
./venv/bin/python3 -m clawdiney.mcp_server > /tmp/mcp_server.log 2>&1 &

# Armazenar o PID do processo em background
MCP_PID=$!
echo "PID do servidor Clawdiney: $MCP_PID"

# Função para encerrar os serviços quando o script for interrompido
cleanup() {
    echo "🛑 Encerrando serviços..."
    docker compose down
    kill $MCP_PID 2>/dev/null || true
    echo "✅ Serviços encerrados."
    exit 0
}

# Registrar a função de cleanup para quando o script for interrompido
trap cleanup SIGINT SIGTERM

echo "✅ Clawdiney iniciado com sucesso!"
echo "   - Neo4j: http://localhost:7474"
echo "   - ChromaDB: http://localhost:8000"
echo "   - Servidor Clawdiney: rodando em background (PID: $MCP_PID)"
echo ""
echo "💡 Para usar com Claude Code:"
echo "   1. Certifique-se de que o MCP está configurado no ~/.claude.json"
echo "   2. Inicie o Claude Code no diretório do projeto"
echo "   3. Use comandos como: 'search_brain para encontrar padrões de arquitetura'"
echo ""
echo "📌 Pressione Ctrl+C para encerrar todos os serviços."

# Manter o script em execução
wait $MCP_PID