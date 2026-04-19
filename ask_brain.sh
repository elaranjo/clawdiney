#!/bin/bash
# Bridge between Claude Code and Clawdiney
# This script is dynamic: it finds its own directory and uses the local venv

# Get the directory where this script is located
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Run the query engine using the venv in the same directory
"$SCRIPT_DIR/venv/bin/python3" "$SCRIPT_DIR/query_engine.py" "$@"
