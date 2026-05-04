#!/bin/bash
# Testes para scripts/migrate_to_multi_vault.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
MIGRATE_SCRIPT="$PROJECT_DIR/scripts/migrate_to_multi_vault.sh"
TEST_DIR="/tmp/clawdiney-test-migration-$$"

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'
PASS=0
FAIL=0

cleanup() {
    rm -rf "$TEST_DIR"
    rm -rf "$HOME/clawdiney-vaults"
}

trap cleanup EXIT

assert() {
    local desc="$1"
    if eval "$2"; then
        echo -e "  ${GREEN}✔${NC} $desc"
        PASS=$((PASS + 1))
    else
        echo -e "  ${RED}✘${NC} $desc"
        FAIL=$((FAIL + 1))
    fi
}

# Setup: create a test vault structure
mkdir -p "$TEST_DIR/vault/30_Resources/SOPs"
mkdir -p "$TEST_DIR/vault/30_Resources/Architecture"
mkdir -p "$TEST_DIR/vault/30_Resources/DesignSystem"
mkdir -p "$TEST_DIR/vault/10_Projects"
mkdir -p "$TEST_DIR/vault/50_Daily"
mkdir -p "$TEST_DIR/vault/20_Areas"
mkdir -p "$TEST_DIR/vault/30_Resources/Learnings"
mkdir -p "$TEST_DIR/vault/SomeOtherFolder"

echo "# SOP Test" > "$TEST_DIR/vault/30_Resources/SOPs/test.md"
echo "# Architecture" > "$TEST_DIR/vault/30_Resources/Architecture/test.md"
echo "# Design" > "$TEST_DIR/vault/30_Resources/DesignSystem/test.md"
echo "# Project X" > "$TEST_DIR/vault/10_Projects/project-x.md"
echo "# Daily note" > "$TEST_DIR/vault/50_Daily/2024-01-01.md"
echo "# Area note" > "$TEST_DIR/vault/20_Areas/health.md"
echo "# Learning note" > "$TEST_DIR/vault/30_Resources/Learnings/test.md"
echo "# Index" > "$TEST_DIR/vault/00_Index.md"
echo "# Agent Protocol" > "$TEST_DIR/vault/Agent_Protocol.md"
echo "# Loose file" > "$TEST_DIR/vault/random.md"
echo "# Other" > "$TEST_DIR/vault/SomeOtherFolder/note.md"

# Create .env with VAULT_PATH pointing to test vault
cat > "$TEST_DIR/.env" << EOF
VAULT_PATH=$TEST_DIR/vault
CHROMA_HOST=localhost
CHROMA_PORT=8000
MODEL_NAME=bge-m3:latest
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=change-this-password
EOF

MIGRATE_CMD="bash $MIGRATE_SCRIPT --project-dir $TEST_DIR"

echo "============================================"
echo "  Testes: migrate_to_multi_vault.sh"
echo "============================================"
echo ""

# Test 1: dry-run não modifica nada
echo -e "${YELLOW}[Teste 1] --dry-run não modifica nada${NC}"
ORIGINAL_ENV=$(cat "$TEST_DIR/.env")
$MIGRATE_CMD --dry-run --force 2>&1 || true
assert "dry-run não modifica .env" 'diff <(echo "$ORIGINAL_ENV") "$TEST_DIR/.env"'
assert "dry-run não cria diretórios general" 'test ! -d "$HOME/clawdiney-vaults/general"'
assert "dry-run não cria diretórios projects" 'test ! -d "$HOME/clawdiney-vaults/projects"'
assert "dry-run não cria diretórios personal" 'test ! -d "$HOME/clawdiney-vaults/personal"'

# Test 2: detecta multi-vault existente e aborta
echo ""
echo -e "${YELLOW}[Teste 2] Detecta multi-vault já existente e aborta${NC}"
cat > "$TEST_DIR/.env" << EOF
VAULTS=general,projects,personal
VAULT_GENERAL_PATH=$TEST_DIR/general
VAULT_PROJECTS_PATH=$TEST_DIR/projects
VAULT_PERSONAL_PATH=$TEST_DIR/personal
EOF
OUTPUT=$($MIGRATE_CMD --force 2>&1 || true)
# Restore single-vault .env
cat > "$TEST_DIR/.env" << EOF
VAULT_PATH=$TEST_DIR/vault
CHROMA_HOST=localhost
CHROMA_PORT=8000
MODEL_NAME=bge-m3:latest
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=change-this-password
EOF
assert "aborta com mensagem de multi-vault ativo" 'echo "$OUTPUT" | grep -q "já está ativo"'

# Test 3: executa migração com --force
echo ""
echo -e "${YELLOW}[Teste 3] Migração completa com --force${NC}"
$MIGRATE_CMD --force 2>&1 || true

assert ".env.backup existe" 'test -f "$TEST_DIR/.env.backup"'
assert "backup contém VAULT_PATH original" 'grep -q "VAULT_PATH=" "$TEST_DIR/.env.backup"'
assert ".env contém VAULTS=" 'grep -q "VAULTS=" "$TEST_DIR/.env"'
assert ".env contém VAULT_GENERAL_PATH" 'grep -q "VAULT_GENERAL_PATH=" "$TEST_DIR/.env"'
assert ".env contém VAULT_PROJECTS_PATH" 'grep -q "VAULT_PROJECTS_PATH=" "$TEST_DIR/.env"'
assert ".env contém VAULT_PERSONAL_PATH" 'grep -q "VAULT_PERSONAL_PATH=" "$TEST_DIR/.env"'

# Test 4: arquivos foram copiados para vaults corretos
echo ""
echo -e "${YELLOW}[Teste 4] Arquivos copiados para vaults corretos${NC}"
assert "SOPs foram para general" 'test -f "$HOME/clawdiney-vaults/general/SOPs/test.md"'
assert "Architecture foi para general" 'test -f "$HOME/clawdiney-vaults/general/Architecture/test.md"'
assert "DesignSystem foi para general" 'test -f "$HOME/clawdiney-vaults/general/DesignSystem/test.md"'
assert "00_Index.md foi para general" 'test -f "$HOME/clawdiney-vaults/general/00_Index.md"'
assert "Agent_Protocol.md foi para general" 'test -f "$HOME/clawdiney-vaults/general/Agent_Protocol.md"'
assert "random.md (solta) foi para general" 'test -f "$HOME/clawdiney-vaults/general/random.md"'
assert "Projects foi para projects" 'test -f "$HOME/clawdiney-vaults/projects/10_Projects/project-x.md"'
assert "Daily foi para personal" 'test -f "$HOME/clawdiney-vaults/personal/50_Daily/2024-01-01.md"'
assert "Areas foi para personal" 'test -f "$HOME/clawdiney-vaults/personal/20_Areas/health.md"'
assert "Learnings foi para personal" 'test -f "$HOME/clawdiney-vaults/personal/Learnings/test.md"'

# Test 5: clawdiney.toml criado em cada vault
echo ""
echo -e "${YELLOW}[Teste 5] clawdiney.toml criado em cada vault${NC}"
assert "clawdiney.toml existe em general" 'test -f "$HOME/clawdiney-vaults/general/clawdiney.toml"'
assert "clawdiney.toml existe em projects" 'test -f "$HOME/clawdiney-vaults/projects/clawdiney.toml"'
assert "clawdiney.toml existe em personal" 'test -f "$HOME/clawdiney-vaults/personal/clawdiney.toml"'
assert "general linked_vaults projects e personal" 'grep -q "linked_vaults = \[\"projects\", \"personal\"\]" "$HOME/clawdiney-vaults/general/clawdiney.toml"'
assert "projects linked_vaults general" 'grep -q "linked_vaults = \[\"general\"\]" "$HOME/clawdiney-vaults/projects/clawdiney.toml"'
assert "personal linked_vaults general" 'grep -q "linked_vaults = \[\"general\"\]" "$HOME/clawdiney-vaults/personal/clawdiney.toml"'

# Test 6: vault original intacto
echo ""
echo -e "${YELLOW}[Teste 6] Vault original não foi modificado${NC}"
assert "vault original ainda existe" 'test -d "$TEST_DIR/vault"'
assert "SOP original intacto" 'test -f "$TEST_DIR/vault/30_Resources/SOPs/test.md"'
assert "vault original tem todos os arquivos" 'test -f "$TEST_DIR/vault/10_Projects/project-x.md"'

echo ""
echo "============================================"
echo -e "  Resultados: ${GREEN}$PASS passaram${NC}, ${RED}$FAIL falharam${NC}"
echo "============================================"

rm -rf "$HOME/clawdiney-vaults"

if [ $FAIL -gt 0 ]; then
    echo -e "${RED}❌ $FAIL teste(s) falharam${NC}"
    exit 1
else
    echo -e "${GREEN}✅ Todos os testes passaram${NC}"
    exit 0
fi
