#!/bin/bash
# Index projects and generate documentation for Obsidian

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

echo "🔍 Clawdiney - Project Indexer"
echo "=============================="
echo ""

# Parse arguments
DRY_RUN=""
VERBOSE=""
VAULT_PATH=""

while [[ $# -gt 0 ]]; do
    case $1 in
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        -v|--verbose)
            VERBOSE="-v"
            shift
            ;;
        --vault)
            VAULT_PATH="--vault $2"
            shift 2
            ;;
        *)
            # Assume it's the projects root path
            PROJECTS_ROOT="$1"
            shift
            ;;
    esac
done

# Default projects root
if [ -z "$PROJECTS_ROOT" ]; then
    PROJECTS_ROOT="$HOME/Documentos/projetos"
fi

# Run the indexer
echo "Indexing projects in: $PROJECTS_ROOT"
echo ""

./venv/bin/python3 -m clawdiney.scripts.index_projects \
    "$PROJECTS_ROOT" \
    $DRY_RUN \
    $VERBOSE \
    $VAULT_PATH

echo ""
echo "✅ Done!"
