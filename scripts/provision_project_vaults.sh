#!/bin/bash
# Clawdiney - Project Vault Provisioning
# Scans ~/projetos/ and creates a vault for each project with a .git directory.
# Every discovered project is linked to "general" by default. To fan a
# project's search out to related projects (e.g. an SDK and the service it
# wraps), edit that vault's clawdiney.toml `linked_vaults` array afterward.
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
        *) echo -e "${RED}Unknown argument: $1${NC}"; exit 1 ;;
    esac
done

SOURCE_DIR="${SOURCE_DIR/#\~/$HOME}"
VAULTS_DIR="${VAULTS_DIR/#\~/$HOME}"

if $DRY_RUN; then
    echo -e "${YELLOW}🔍 DRY-RUN MODE — No changes will be made${NC}"
fi

echo -e "${BLUE}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  Clawdiney - Vault Provisioning                ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${CYAN}Source directory:${NC} $SOURCE_DIR"
echo -e "${CYAN}Vaults directory:${NC} $VAULTS_DIR"
echo ""

if [ ! -d "$SOURCE_DIR" ]; then
    echo -e "${RED}❌ Source directory not found: $SOURCE_DIR${NC}"
    exit 1
fi

IGNORE_DIRS=("venv" ".claude" ".docker")

# =====================================================
# 1. GENERAL VAULT
# =====================================================
echo -e "${GREEN}📁 [1/2] Creating general vault...${NC}"

GENERAL_DIR="$VAULTS_DIR/general"
if [ ! -d "$GENERAL_DIR" ] || [ ! -f "$GENERAL_DIR/clawdiney.toml" ]; then
    if $DRY_RUN; then
        echo -e "${YELLOW}  -> Would create: $GENERAL_DIR/ (linked_vaults = [])${NC}"
    else
        mkdir -p "$GENERAL_DIR"
        cat > "$GENERAL_DIR/clawdiney.toml" << 'EOF'
id = "general"
name = "General Vault"
description = "Shared knowledge: SOPs, Architecture, Design System"
linked_vaults = []
EOF
        echo -e "${GREEN}  ✅ general vault created${NC}"
    fi
else
    echo -e "${YELLOW}  ⏭️  general vault already exists${NC}"
fi

# =====================================================
# 2. PROJECTS
# =====================================================
echo ""
echo -e "${GREEN}📁 [2/2] Scanning projects in $SOURCE_DIR...${NC}"

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
        DESC="Clawdiney project (isolated)"
    else
        LINKED='["general"]'
        DESC="Project $name"
    fi

    VAULT_DIR="$VAULTS_DIR/$name"
    if [ -d "$VAULT_DIR" ] && [ -f "$VAULT_DIR/clawdiney.toml" ]; then
        echo -e "${YELLOW}  ⏭️  $name: vault already exists${NC}"
        continue
    fi

    if $DRY_RUN; then
        echo -e "${YELLOW}  -> Would create: $name/ (linked: $LINKED)${NC}"
    else
        mkdir -p "$VAULT_DIR"
        cat > "$VAULT_DIR/clawdiney.toml" << TOMLEOF
id = "$name"
name = "$name"
description = "$DESC"
linked_vaults = $LINKED
TOMLEOF
        echo -e "${GREEN}  ✅ $name: vault created (linked: $LINKED)${NC}"
        CREATED=$((CREATED + 1))
    fi
done

# =====================================================
# SUMMARY
# =====================================================
echo ""
echo -e "${BLUE}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  SUMMARY                                       ║${NC}"
echo -e "${BLUE}╚══════════════════════════════════════════════════╝${NC}"
echo -e "${CYAN}Projects found:${NC} $FOUND"

if $DRY_RUN; then
    echo -e "${YELLOW}Dry-run — nothing was created. Remove --dry-run to execute.${NC}"
    echo ""
    echo -e "${CYAN}Plan summary:${NC}"
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
        else
            echo "  $name       linked_vaults = [\"general\"]"
        fi
    done
else
    echo -e "${GREEN}Vaults created:${NC} $CREATED (+ general)"
    echo -e "${CYAN}Total:${NC} $((CREATED + 1)) vaults"
    echo ""
    echo -e "${GREEN}✅ Provisioning complete!${NC}"
    echo ""
    echo -e "${CYAN}Next steps:${NC}"
    echo "  1. Migrate the general vault:"
    echo "     cp -r ~/Documents/ObsidianVault/* $VAULTS_DIR/general/"
    echo "  2. Index everything:"
    echo "     $SCRIPT_DIR/../venv/bin/python -m clawdiney.indexer"
    echo "  3. Verify:"
    echo "     $SCRIPT_DIR/../venv/bin/python -m clawdiney.mcp_server"
    echo ""
    echo -e "${CYAN}Tip:${NC} to link related projects (e.g. an SDK and the"
    echo "  service it wraps) for broader search fallback, edit the"
    echo "  linked_vaults array in that project's clawdiney.toml."
    echo ""
    echo -e "${CYAN}Structure created:${NC}"
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
