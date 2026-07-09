# Project Watcher - Auto-Sync for Obsidian

## Overview

The Project Watcher is a service that automatically monitors changes in your projects and updates the Obsidian documentation in real time.

## Why use it?

**Problem:** During day-to-day work, it's easy to forget to manually sync code changes with Obsidian.

**Solution:** The watcher runs in the background and automatically detects file changes, reindexing affected projects after a 10-second debounce.

## Quick Install

### Option 1: Control scripts (recommended for development)

```bash
# Start the watcher
./scripts/start_watcher.sh

# Stop the watcher
./scripts/stop_watcher.sh

# View live logs
tail -f logs/watcher.log
```

### Option 2: systemd service (production / auto-start)

```bash
# Install the service
sudo cp scripts/clawdiney-watcher.service /etc/systemd/system/

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable clawdiney-watcher
sudo systemctl start clawdiney-watcher

# Check status
sudo systemctl status clawdiney-watcher

# View logs via journalctl
journalctl -u clawdiney-watcher -f
```

## How It Works

### Watched Files

The watcher detects changes in files with these extensions:
- `.py`, `.ts`, `.js`, `.tsx`, `.jsx` - Code
- `.json`, `.toml`, `.yaml`, `.yml` - Configuration
- `.md`, `.txt` - Documentation
- `.sql`, `.prisma`, `.graphql` - Database

### High Priority

These files always trigger immediate reindexing:
- `package.json`
- `pyproject.toml`
- `setup.py`
- `requirements.txt`
- `Cargo.toml`
- `go.mod`
- `tsconfig.json`
- `docker-compose.yml`

### Ignored Directories

These directories are automatically ignored:
- `__pycache__`, `.venv`, `venv`
- `node_modules`
- `.git`, `.github`
- `dist`, `build`, `coverage`
- `target`, `vendor`
- Hidden files (`.hidden`)

### Debounce

Rapid changes are batched together:
- **Debounce:** 10 seconds after the last change
- **Batch:** Changes within 2 seconds are treated as a single batch

## Usage Example

1. **Start the watcher:**
   ```bash
   ./scripts/start_watcher.sh
   ```

2. **Work on your code as usual**

3. **The watcher detects and syncs automatically:**
   ```
   2026-04-24 13:45:27 [INFO] 🔴 High-priority change in my-project - will reindex soon
   2026-04-24 13:45:37 [INFO] 🔄 Reindexing projects: my-project
   2026-04-24 13:45:40 [INFO] ✅ Updated: my-project
   ```

4. **Check the updated documentation in Obsidian:**
   - File: `00_Inbox/Projects/my-project.md`

## Configuration

### Change the projects directory

Edit `scripts/start_watcher.sh`:
```bash
PROJECTS_ROOT="${PROJECTS_ROOT:-$HOME/Documents/projects}"
```

Or set the environment variable:
```bash
export PROJECTS_ROOT=~/my-projects
./scripts/start_watcher.sh
```

### Change the Obsidian directory

Edit `scripts/clawdiney-watcher.service` or pass it on the command line:
```bash
./venv/bin/python3 -m clawdiney.scripts.watch_projects ~/projects --vault ~/MyObsidian
```

## Troubleshooting

### Watcher doesn't start

Check that the virtual environment is active:
```bash
ls -la venv/bin/python3
```

### Logs show path errors

Check that the directories exist:
```bash
ls -la ~/Documents/projects
ls -la ~/Documents/ObsidianVault
```

### Watcher using too much CPU

Check that it isn't monitoring directories with heavy change activity:
```bash
tail -f logs/watcher.log | grep "Change detected"
```

If needed, add more directories to the `IGNORE_DIRS` list in `src/clawdiney/scripts/watch_projects.py`.

### Stop the systemd service

```bash
sudo systemctl stop clawdiney-watcher
sudo systemctl disable clawdiney-watcher
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Project Watcher                          │
├─────────────────────────────────────────────────────────────┤
│  FileSystemEventHandler (watchdog)                          │
│  │                                                          │
│  ├── on_modified() ──┐                                      │
│  ├── on_created()  ──┼──> _schedule_reindex() ──┐          │
│  └── on_deleted()  ──┘                          │          │
│                                                 ▼          │
│  Background Loop:                                      │
│  ┌──────────────────────────────────────────────────┐    │
│  │  Every 1 second:                                 │    │
│  │  1. Check pending projects                       │    │
│  │  2. Apply debounce (10s)                         │    │
│  │  3. Call ProjectIndexer to reindex               │    │
│  │  4. Save .md to Obsidian                         │    │
│  └──────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Useful Commands

```bash
# Check if it's running
ps aux | grep watch_projects

# View PID
cat logs/watcher.pid

# Restart
./scripts/stop_watcher.sh && ./scripts/start_watcher.sh

# Last 100 log lines
tail -100 logs/watcher.log
```
