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
