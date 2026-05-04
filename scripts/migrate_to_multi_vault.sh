#!/bin/bash
# Clawdiney - Migração para Multi-Vault
# Transforma um vault único em três vaults (general, projects, personal)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Cores
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

DRY_RUN=false
FORCE=false

# Processa argumentos
while [ $# -gt 0 ]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --force) FORCE=true; shift ;;
        --project-dir) PROJECT_DIR="$2"; shift 2 ;;
        *) echo -e "${RED}Argumento desconhecido: $1${NC}"; exit 1 ;;
    esac
done

echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BLUE}  Clawdiney - Migração para Multi-Vault${NC}"
echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

# 1. Verifica .env
ENV_FILE="$PROJECT_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
    echo -e "${RED}❌ .env não encontrado em $ENV_FILE${NC}"
    echo "   Crie o .env a partir do .env.example antes de migrar."
    exit 1
fi

# 2. Detecta se já está em multi-vault
if grep -q "^VAULTS=" "$ENV_FILE" 2>/dev/null; then
    echo -e "${RED}❌ Modo multi-vault já está ativo!${NC}"
    echo "   O arquivo .env já contém VAULTS=."
    echo "   Nada a fazer — abortando."
    exit 1
fi

# 3. Lê VAULT_PATH do .env
source "$ENV_FILE"

if [ -z "$VAULT_PATH" ]; then
    echo -e "${RED}❌ VAULT_PATH não definido no .env${NC}"
    exit 1
fi

VAULT_PATH="${VAULT_PATH/#\~/$HOME}"

if [ ! -d "$VAULT_PATH" ]; then
    echo -e "${RED}❌ Diretório VAULT_PATH não existe: $VAULT_PATH${NC}"
    exit 1
fi

echo -e "${CYAN}📂 Vault de origem:${NC} $VAULT_PATH"
echo ""

# 4. Define paths destino
VAULT_GENERAL_PATH="$HOME/clawdiney-vaults/general"
VAULT_PROJECTS_PATH="$HOME/clawdiney-vaults/projects"
VAULT_PERSONAL_PATH="$HOME/clawdiney-vaults/personal"

# 5. Mapa de migração
declare -A MIGRATION_MAP=(
    ["30_Resources/SOPs"]="general"
    ["30_Resources/Architecture"]="general"
    ["30_Resources/DesignSystem"]="general"
    ["10_Projects"]="projects"
    ["50_Daily"]="personal"
    ["20_Areas"]="personal"
    ["30_Resources/Learnings"]="personal"
)

TOP_LEVEL_GENERAL_FILES=(
    "00_Index.md"
    "Agent_Protocol.md"
)

echo -e "${YELLOW}📋 Plano de migração:${NC}"
echo ""
echo -e "  ${CYAN}general vault:${NC}  $VAULT_GENERAL_PATH"
for dir in "${!MIGRATION_MAP[@]}"; do
    if [ "${MIGRATION_MAP[$dir]}" = "general" ]; then
        echo -e "    - $dir/  →  general/"
    fi
done
for f in "${TOP_LEVEL_GENERAL_FILES[@]}"; do
    echo -e "    - $f  →  general/"
done
echo -e "    - (outros arquivos soltos)  →  general/"
echo ""
echo -e "  ${CYAN}projects vault:${NC} $VAULT_PROJECTS_PATH"
for dir in "${!MIGRATION_MAP[@]}"; do
    if [ "${MIGRATION_MAP[$dir]}" = "projects" ]; then
        echo -e "    - $dir/  →  projects/"
    fi
done
echo ""
echo -e "  ${CYAN}personal vault:${NC} $VAULT_PERSONAL_PATH"
for dir in "${!MIGRATION_MAP[@]}"; do
    if [ "${MIGRATION_MAP[$dir]}" = "personal" ]; then
        echo -e "    - $dir/  →  personal/"
    fi
done

echo ""

if [ "$DRY_RUN" = true ]; then
    echo -e "${YELLOW}📌 Modo --dry-run: nenhuma alteração foi feita.${NC}"
    echo -e "${YELLOW}   Execute sem --dry-run para aplicar a migração.${NC}"
    exit 0
fi

# Confirmação
if [ "$FORCE" = false ]; then
    echo -e "${YELLOW}⚠️  Esta operação vai COPIAR arquivos do vault atual para novos vaults.${NC}"
    echo -e "${YELLOW}   O vault original NÃO será modificado.${NC}"
    read -p "$(echo -e ${YELLOW}"Continuar? (s/N): "${NC})" CONFIRM
    if [[ ! "$CONFIRM" =~ ^[Ss]$ ]]; then
        echo -e "${RED}❌ Operação cancelada.${NC}"
        exit 0
    fi
fi

# 6. Backup do .env
BACKUP_FILE="$ENV_FILE.backup"
cp "$ENV_FILE" "$BACKUP_FILE"
echo -e "${GREEN}✅ Backup do .env criado: $BACKUP_FILE${NC}"

# 7. Cria diretórios destino
mkdir -p "$VAULT_GENERAL_PATH"
mkdir -p "$VAULT_PROJECTS_PATH"
mkdir -p "$VAULT_PERSONAL_PATH"
echo -e "${GREEN}✅ Diretórios destino criados${NC}"

# 8. Copia arquivos conforme o mapa
copy_to_vault() {
    local src="$1"
    local dest="$2"
    local label="$3"
    if [ -d "$src" ]; then
        cp -r "$src" "$dest/"
        echo -e "${GREEN}  ✔ Copiado:${NC} $label"
    else
        echo -e "${YELLOW}  ⚠ Diretório não encontrado (ignorado):${NC} $label"
    fi
}

copy_file_to_vault() {
    local src="$1"
    local dest="$2"
    if [ -f "$src" ]; then
        cp "$src" "$dest/"
        echo -e "${GREEN}  ✔ Copiado:${NC} $(basename "$src")"
    else
        echo -e "${YELLOW}  ⚠ Arquivo não encontrado (ignorado):${NC} $(basename "$src")"
    fi
}

echo ""
echo -e "${BLUE}📂 Copiando arquivos...${NC}"

for dir in "${!MIGRATION_MAP[@]}"; do
    src="$VAULT_PATH/$dir"
    case "${MIGRATION_MAP[$dir]}" in
        general)  dest="$VAULT_GENERAL_PATH" ;;
        projects) dest="$VAULT_PROJECTS_PATH" ;;
        personal) dest="$VAULT_PERSONAL_PATH" ;;
    esac
    copy_to_vault "$src" "$dest" "$dir/ → ${MIGRATION_MAP[$dir]}/"
done

# Copia arquivos de topo para general
for f in "${TOP_LEVEL_GENERAL_FILES[@]}"; do
    copy_file_to_vault "$VAULT_PATH/$f" "$VAULT_GENERAL_PATH"
done

# Copia outros arquivos soltos (markdown na raiz) para general
while IFS= read -r -d '' file; do
    rel="${file#$VAULT_PATH/}"
    # Pula diretórios que já foram mapeados
    skip=false
    for dir in "${!MIGRATION_MAP[@]}"; do
        if [[ "$rel" == "$dir"/* ]] || [ "$rel" = "$dir" ]; then
            skip=true
            break
        fi
    done
    if [ "$skip" = false ] && [ "$(dirname "$rel")" = "." ]; then
        copy_file_to_vault "$file" "$VAULT_GENERAL_PATH"
    fi
done < <(find "$VAULT_PATH" -maxdepth 1 -name "*.md" -print0)

echo -e "${GREEN}✅ Arquivos copiados${NC}"

# 9. Cria clawdiney.toml para cada vault
echo ""
echo -e "${BLUE}📝 Criando clawdiney.toml...${NC}"

cat > "$VAULT_GENERAL_PATH/clawdiney.toml" << 'TOML'
id = "general"
name = "General Vault"
linked_vaults = ["projects", "personal"]
TOML
echo -e "${GREEN}  ✔ clawdiney.toml criado em:${NC} general"

cat > "$VAULT_PROJECTS_PATH/clawdiney.toml" << 'TOML'
id = "projects"
name = "Projects Vault"
linked_vaults = ["general"]
TOML
echo -e "${GREEN}  ✔ clawdiney.toml criado em:${NC} projects"

cat > "$VAULT_PERSONAL_PATH/clawdiney.toml" << 'TOML'
id = "personal"
name = "Personal Vault"
linked_vaults = ["general"]
TOML
echo -e "${GREEN}  ✔ clawdiney.toml criado em:${NC} personal"

# 10. Atualiza .env com multi-vault config
echo ""
echo -e "${BLUE}📝 Atualizando .env para multi-vault...${NC}"

cat > "$ENV_FILE" << ENVEOF
# --- Clawdiney Multi-Vault Configuration ---

# Lista de vaults (separados por vírgula)
VAULTS=general,projects,personal

# Paths para cada vault
VAULT_GENERAL_PATH=$VAULT_GENERAL_PATH
VAULT_PROJECTS_PATH=$VAULT_PROJECTS_PATH
VAULT_PERSONAL_PATH=$VAULT_PERSONAL_PATH

# Vault padrão usado pelo MCP server
MCP_DEFAULT_VAULT=general

# ChromaDB HTTP connection
CHROMA_HOST=localhost
CHROMA_PORT=8000

# Embedding model to use via Ollama
MODEL_NAME=bge-m3:latest

# Optional reranker
ENABLE_RERANK=true
RERANK_MODEL_NAME=cross-encoder/ms-marco-MiniLM-L-6-v2
RERANK_THRESHOLD=0.5

# Chunking
CHUNKING_STRATEGY=headers
CHUNK_SIZE=500
CHUNK_OVERLAP=50

# Neo4j Connection Details
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=change-this-password

# Container images
NEO4J_IMAGE=neo4j:latest
CHROMA_IMAGE=chromadb/chroma:latest

# Ollama host for Dockerized MCP server
OLLAMA_HOST=host.docker.internal

# Redis (Query Cache)
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=changeme  # Change in production!
ENABLE_QUERY_CACHE=true
ENVEOF

echo -e "${GREEN}✅ .env atualizado para multi-vault${NC}"
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  ✅ Migração concluída com sucesso!${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo -e "  Backup do .env original: ${CYAN}$BACKUP_FILE${NC}"
echo -e "  Vault general:           ${CYAN}$VAULT_GENERAL_PATH${NC}"
echo -e "  Vault projects:          ${CYAN}$VAULT_PROJECTS_PATH${NC}"
echo -e "  Vault personal:          ${CYAN}$VAULT_PERSONAL_PATH${NC}"
echo ""
echo -e "${YELLOW}⚠️  Importante: reindexe o vault para o novo layout:${NC}"
echo -e "   ./venv/bin/python3 -m clawdiney.indexer"
echo ""
