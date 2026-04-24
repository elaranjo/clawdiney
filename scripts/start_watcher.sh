#!/bin/bash
# Start Project Watcher as a background daemon

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Configuration
PROJECTS_ROOT="${PROJECTS_ROOT:-$HOME/Documentos/projetos}"
LOG_DIR="$PROJECT_DIR/logs"
PID_FILE="$LOG_DIR/watcher.pid"
LOG_FILE="$LOG_DIR/watcher.log"

# Create log directory
mkdir -p "$LOG_DIR"

# Check if already running
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    if kill -0 "$PID" 2>/dev/null; then
        echo "⚠️  Watcher already running (PID: $PID)"
        echo "To stop: $SCRIPT_DIR/stop_watcher.sh"
        exit 0
    else
        echo "🧹 Removing stale PID file"
        rm -f "$PID_FILE"
    fi
fi

echo "🚀 Starting Project Watcher..."
echo "📁 Watching: $PROJECTS_ROOT"
echo "📝 Logging to: $LOG_FILE"

# Start watcher in background
nohup ./venv/bin/python3 -m clawdiney.scripts.watch_projects "$PROJECTS_ROOT" \
    > "$LOG_FILE" 2>&1 &

# Save PID
echo $! > "$PID_FILE"

sleep 2

# Verify it started
if kill -0 $(cat "$PID_FILE") 2>/dev/null; then
    echo "✅ Watcher started (PID: $(cat "$PID_FILE"))"
    echo "To stop: $SCRIPT_DIR/stop_watcher.sh"
    echo "To view logs: tail -f $LOG_FILE"
else
    echo "❌ Failed to start watcher"
    rm -f "$PID_FILE"
    exit 1
fi
