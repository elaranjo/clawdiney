#!/bin/bash

# Run unit tests for Clawdiney
echo "Running unit tests..."

# Ensure we're in the project directory
cd "$(dirname "$0")"

# Run the tests
./venv/bin/python3 -m pytest test_brain_engine.py -v

echo "Tests completed!"