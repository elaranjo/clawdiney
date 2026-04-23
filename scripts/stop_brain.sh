#!/bin/bash
# Script para parar todos os serviços do Clawdiney

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🛑 Parando Clawdiney..."

# Parar os containers Docker
echo "🐳 Parando containers Docker..."
docker compose down

echo "✅ Clawdiney parado com sucesso!"