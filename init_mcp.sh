#!/bin/bash
# Script para inicializar o servidor MCP do Clawdiney
# Este script primeiro indexa o vault e depois inicia o servidor MCP

set -e

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

# Indexar o vault (se houver arquivos)
echo "🔍 Indexando o vault..."
if [ -f "/app/brain_indexer.py" ]; then
    echo "   Executando brain_indexer.py..."
    python /app/brain_indexer.py
else
    echo "   brain_indexer.py não encontrado. Pulando indexação."
fi

echo "🚀 Iniciando servidor MCP..."
exec python /app/mcp_wrapper.py