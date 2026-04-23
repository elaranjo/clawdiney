#!/bin/bash
# Bridge between Claude Code and Clawdiney
# This script is dynamic: it finds its own directory and uses the local venv

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

# Run the query engine using the venv in the same directory
cd "$PROJECT_DIR"
"$SCRIPT_DIR/venv/bin/python3" -m clawdiney.query_engine "$@"
