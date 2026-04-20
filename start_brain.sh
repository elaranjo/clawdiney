#!/bin/bash
# Script para iniciar todos os serviços do Clawdiney

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🚀 Iniciando Clawdiney..."

# Verificar se o Docker está disponível
if ! command -v docker &> /dev/null; then
    echo "❌ Docker não encontrado. Por favor, instale o Docker primeiro."
    exit 1
fi

# Verificar se o Ollama está disponível
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama não encontrado. Por favor, instale o Ollama primeiro."
    exit 1
fi

# Verificar se o modelo bge-m3 está disponível
echo "🔍 Verificando modelo bge-m3..."
if ! ollama list | grep -q "bge-m3"; then
    echo "📥 Baixando modelo bge-m3..."
    ollama pull bge-m3
fi

# Iniciar os containers Docker
echo "🐳 Iniciando containers Docker..."
docker compose up -d

# Aguardar alguns segundos para os serviços iniciarem
echo "⏳ Aguardando inicialização dos serviços..."
sleep 10

# Verificar se os serviços estão rodando
echo "🔍 Verificando status dos serviços..."
docker compose ps

echo "✅ Clawdiney iniciado com sucesso!"
echo "   - Neo4j: http://localhost:7474"
echo "   - ChromaDB: http://localhost:8000"
echo "   - MCP Server: localhost:8006 (para integração com Claude Code)"

# Instruções para uso
echo ""
echo "💡 Para usar com Claude Code:"
echo "   1. Certifique-se de que o MCP está configurado no ~/.claude.json"
echo "   2. Inicie o Claude Code no diretório do projeto"
echo "   3. Use comandos como: 'search_brain para encontrar padrões de arquitetura'"