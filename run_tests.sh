#!/bin/bash

# Run default unit tests for Clawdiney
echo "Running unit tests..."

# Ensure we're in the project directory
cd "$(dirname "$0")"

# Run the default unit suite.
./venv/bin/python3 -m pytest test_brain_engine.py -v

echo "Unit tests completed!"
echo "To run integration tests, execute: RUN_BRAIN_INTEGRATION=1 ./venv/bin/python3 -m pytest test_brain_engine_pytest.py -v"
