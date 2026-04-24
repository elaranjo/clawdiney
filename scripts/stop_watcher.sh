#!/bin/bash
# Stop Project Watcher daemon

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PID_FILE="$PROJECT_DIR/logs/watcher.pid"

if [ ! -f "$PID_FILE" ]; then
    echo "⚠️  Watcher is not running (no PID file)"
    exit 0
fi

PID=$(cat "$PID_FILE")

if ! kill -0 "$PID" 2>/dev/null; then
    echo "🧹 Removing stale PID file"
    rm -f "$PID_FILE"
    exit 0
fi

echo "⏹️  Stopping Watcher (PID: $PID)..."
kill "$PID"

# Wait for graceful shutdown
for i in {1..10}; do
    if ! kill -0 "$PID" 2>/dev/null; then
        echo "✅ Watcher stopped"
        rm -f "$PID_FILE"
        exit 0
    fi
    sleep 1
done

# Force kill if still running
echo "⚠️  Force stopping..."
kill -9 "$PID" 2>/dev/null || true
rm -f "$PID_FILE"
echo "✅ Watcher stopped"
