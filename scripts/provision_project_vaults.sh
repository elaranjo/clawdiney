#!/bin/bash
# Clawdiney - Provisionamento de Vaults de Projeto
# Escaneia ~/projetos/ e cria um vault para cada projeto com .git
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; NC='\033[0m'

DRY_RUN=false
SOURCE_DIR="$HOME/projetos"
VAULTS_DIR="$HOME/clawdiney-vaults"

while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --source-dir) SOURCE_DIR="$2"; shift 2 ;;
        --vaults-dir) VAULTS_DIR="$2"; shift 2 ;;
        *) echo -e "${RED}Argumento desconhecido: $1${NC}"; exit 1 ;;
    esac
done

SOURCE_DIR="${SOURCE_DIR/#\~/$HOME}"
VAULTS_DIR="${VAULTS_DIR/#\~/$HOME}"

if $DRY_RUN; then
    echo -e "${YELLOW}🔍 MODO DRY-RUN — Nenhuma alteração será feita${NC}"
fi

echo -e "${BLUE}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Clawdiney - Provisionamento de Vaults         ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Diretório fonte:${NC}  $SOURCE_DIR"
echo -e "${CYAN}Diretório vaults:${NC} $VAULTS_DIR"
echo ""

if [ ! -d "$SOURCE_DIR" ]; then
    echo -e "${RED}❌ Diretório fonte não encontrado: $SOURCE_DIR${NC}"
    exit 1
fi

declare -A SDK_PARENT
SDK_PARENT["Budget-SDK"]="Budget"
SDK_PARENT["Company-SDK"]="Company"
SDK_PARENT["User-SDK"]="User"
SDK_PARENT["credit-sdk"]="credit"

IGNORE_DIRS=("venv" ".claude" ".docker")

# =====================================================
# 1. GENERAL
# =====================================================
echo -e "${GREEN}📁 [1/2] Criando vault general...${NC}"

GENERAL_DIR="$VAULTS_DIR/general"
if [ ! -d "$GENERAL_DIR" ] || [ ! -f "$GENERAL_DIR/clawdiney.toml" ]; then
    if $DRY_RUN; then
        echo -e "${YELLOW}  -> Criaria: $GENERAL_DIR/ (linked_vaults = [])${NC}"
    else
        mkdir -p "$GENERAL_DIR"
        cat > "$GENERAL_DIR/clawdiney.toml" << 'EOF'
id = "general"
name = "General Vault"
description = "Conhecimento compartilhado: SOPs, Arquitetura, Design System"
linked_vaults = []
EOF
        echo -e "${GREEN}  ✅ Vault general criado${NC}"
    fi
else
    echo -e "${YELLOW}  ⏭️  Vault general já existe${NC}"
fi

# =====================================================
# 2. PROJETOS
# =====================================================
echo ""
echo -e "${GREEN}📁 [2/2] Escaneando projetos em $SOURCE_DIR...${NC}"

FOUND=0
CREATED=0

for entry in "$SOURCE_DIR"/*/; do
    name=$(basename "$entry")

    skip=false
    for ig in "${IGNORE_DIRS[@]}"; do
        [ "$name" == "$ig" ] && skip=true && break
    done
    $skip && continue

    [ ! -d "$entry/.git" ] && continue

    FOUND=$((FOUND + 1))

    if [ "$name" == "clawdiney" ]; then
        LINKED="[]"
        DESC="Projeto Clawdiney (isolado)"
    elif [ -n "${SDK_PARENT[$name]:-}" ]; then
        LINKED="[\"general\", \"${SDK_PARENT[$name]}\"]"
        DESC="SDK de ${SDK_PARENT[$name]}"
    else
        LINKED='["general"]'
        DESC="Projeto $name"
    fi

    VAULT_DIR="$VAULTS_DIR/$name"
    if [ -d "$VAULT_DIR" ] && [ -f "$VAULT_DIR/clawdiney.toml" ]; then
        echo -e "${YELLOW}  ⏭️  $name: vault já existe${NC}"
        continue
    fi

    if $DRY_RUN; then
        echo -e "${YELLOW}  -> Criaria: $name/ (linked: $LINKED)${NC}"
    else
        mkdir -p "$VAULT_DIR"
        cat > "$VAULT_DIR/clawdiney.toml" << TOMLEOF
id = "$name"
name = "$name"
description = "$DESC"
linked_vaults = $LINKED
TOMLEOF
        echo -e "${GREEN}  ✅ $name: vault criado (linked: $LINKED)${NC}"
        CREATED=$((CREATED + 1))
    fi
done

# =====================================================
# RESUMO
# =====================================================
echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  RESUMO                                        ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════╝${NC}"
echo -e "${CYAN}Projetos encontrados:${NC} $FOUND"

if $DRY_RUN; then
    echo -e "${YELLOW}Dry-run — nada foi criado. Remova --dry-run para executar.${NC}"
    echo ""
    echo -e "${CYAN}Resumo do plano:${NC}"
    echo "  general     linked_vaults = []"
    for entry in "$SOURCE_DIR"/*/; do
        name=$(basename "$entry")
        skip=false
        for ig in "${IGNORE_DIRS[@]}"; do
            [ "$name" == "$ig" ] && skip=true && break
        done
        $skip && continue
        [ ! -d "$entry/.git" ] && continue

        if [ "$name" == "clawdiney" ]; then
            echo "  $name       linked_vaults = []"
        elif [ -n "${SDK_PARENT[$name]:-}" ]; then
            echo "  $name       linked_vaults = [\"general\", \"${SDK_PARENT[$name]}\"]"
        else
            echo "  $name       linked_vaults = [\"general\"]"
        fi
    done
else
    echo -e "${GREEN}Vaults criados:${NC} $CREATED (+ general)"
    echo -e "${CYAN}Total:${NC} $((CREATED + 1)) vaults"
    echo ""
    echo -e "${GREEN}✅ Provisionamento concluído!${NC}"
    echo ""
    echo -e "${CYAN}Próximos passos:${NC}"
    echo "  1. Migrar vault geral:"
    echo "     cp -r ~/Documents/ObsidianVault/* $VAULTS_DIR/general/"
    echo "  2. Indexar tudo:"
    echo "     $SCRIPT_DIR/../venv/bin/python -m clawdiney.indexer"
    echo "  3. Verificar:"
    echo "     $SCRIPT_DIR/../venv/bin/python -m clawdiney.mcp_server"
    echo ""
    echo -e "${CYAN}Estrutura criada:${NC}"
    ls -d "$VAULTS_DIR"/*/ 2>/dev/null | while read vdir; do
        vname=$(basename "$vdir")
        toml="$vdir/clawdiney.toml"
        if [ -f "$toml" ]; then
            linked=$(grep "^linked_vaults" "$toml" | head -1)
            echo -e "  ${GREEN}📁 $vname${NC} $linked"
        fi
    done
fi

chmod +x "$0"
