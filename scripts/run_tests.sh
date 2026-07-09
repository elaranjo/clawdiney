#!/bin/bash

# Run default unit tests for Clawdiney
echo "Running unit tests..."

# Ensure we're in the project directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Run the default unit suite.
./venv/bin/python3 -m pytest tests/ -v

echo "Unit tests completed!"

# Retrieval eval harness (recall@k/MRR/hit-rate regression gate) needs Ollama
# running with the embedding model pulled — skip gracefully if unavailable
# rather than failing CI/dev environments that don't have it.
echo ""
echo "Running retrieval eval harness..."
if curl -s -m 2 http://localhost:11434/api/tags >/dev/null 2>&1; then
    ./venv/bin/clawdiney-eval --all-modes
    echo "Eval harness completed!"
else
    echo "Ollama not reachable at localhost:11434 — skipping eval harness."
fi
