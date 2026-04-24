#!/usr/bin/env python3
"""
File Watcher for Project Indexing.

Monitors project directories for changes and automatically regenerates
Obsidian documentation when relevant files are modified.

Usage:
    python -m clawdiney.scripts.watch_projects ~/Documentos/projetos

Runs continuously until interrupted (Ctrl+C).
"""

import logging
import sys
import time
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event, Thread

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from clawdiney.project_indexer import ProjectIndexer

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)

# Files that trigger reindex when changed
RELEVANT_EXTENSIONS = {
    ".py",
    ".ts",
    ".js",
    ".tsx",
    ".jsx",
    ".json",
    ".toml",
    ".yaml",
    ".yml",
    ".md",
    ".txt",
    ".sql",
    ".prisma",
    ".graphql",
}

# Files that ALWAYS trigger reindex (high priority)
HIGH_PRIORITY_FILES = {
    "package.json",
    "pyproject.toml",
    "setup.py",
    "requirements.txt",
    "Cargo.toml",
    "go.mod",
    "tsconfig.json",
    "docker-compose.yml",
}

# Directories to ignore
IGNORE_DIRS = {
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    ".git",
    "dist",
    "build",
    "coverage",
    ".pytest_cache",
    "target",
    "vendor",
}

# Debounce settings
DEBOUNCE_SECONDS = 10  # Wait 10s after last change before reindexing
BATCH_SECONDS = 2  # Group changes within 2s as single batch


class ProjectWatchHandler(FileSystemEventHandler):
    """Handles file system events and triggers reindexing."""

    def __init__(
        self,
        projects_root: Path,
        vault_path: Path,
        obsidian_folder: str,
    ):
        super().__init__()
        self.projects_root = projects_root.resolve()
        self.vault_path = vault_path
        self.obsidian_folder = obsidian_folder

        # Track pending reindex per project
        self._pending_projects: dict[str, datetime] = defaultdict(lambda: datetime.min)
        self._lock = Thread()
        self._reindex_event = Event()
        self._last_event_time: dict[str, datetime] = {}

        logger.info(f"Watching projects in: {self.projects_root}")

    def _should_ignore(self, path: Path) -> bool:
        """Check if path should be ignored."""
        # Check if any parent directory is in ignore list
        for part in path.parts:
            if part in IGNORE_DIRS:
                return True

        # Check if it's a hidden file/directory
        if any(part.startswith(".") for part in path.parts):
            return True

        # Check extension
        if path.suffix.lower() not in RELEVANT_EXTENSIONS:
            return True

        return False

    def _is_high_priority(self, path: Path) -> bool:
        """Check if file change should trigger immediate reindex."""
        return path.name in HIGH_PRIORITY_FILES

    def _get_project_name(self, file_path: Path) -> str | None:
        """Extract project name from file path."""
        try:
            relative = file_path.relative_to(self.projects_root)
            return relative.parts[0] if relative.parts else None
        except ValueError:
            return None

    def _schedule_reindex(self, project_name: str, high_priority: bool = False):
        """Schedule a project for reindexing."""
        now = datetime.now()
        self._pending_projects[project_name] = now

        if high_priority:
            logger.info(f"🔴 High-priority change in {project_name} - will reindex soon")
        else:
            logger.debug(f"Change detected in {project_name}")

        self._reindex_event.set()

    def on_modified(self, event: FileSystemEvent):
        """Handle file modification events."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        if self._should_ignore(file_path):
            return

        project_name = self._get_project_name(file_path)
        if not project_name:
            return

        high_priority = self._is_high_priority(file_path)
        self._schedule_reindex(project_name, high_priority)

    def on_created(self, event: FileSystemEvent):
        """Handle file creation events."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)

        if self._should_ignore(file_path):
            return

        project_name = self._get_project_name(file_path)
        if not project_name:
            return

        # New files are always high priority
        self._schedule_reindex(project_name, high_priority=True)

    def on_deleted(self, event: FileSystemEvent):
        """Handle file deletion events."""
        if event.is_directory:
            return

        file_path = Path(event.src_path)
        project_name = self._get_project_name(file_path)
        if not project_name:
            return

        # Deletions are high priority
        self._schedule_reindex(project_name, high_priority=True)
        logger.info(f"🗑️ File deleted in {project_name}")


class WatcherService:
    """Manages the file watcher and reindexing loop."""

    def __init__(
        self,
        projects_root: Path,
        vault_path: Path,
        obsidian_folder: str = "00_Inbox/Projetos",
    ):
        self.projects_root = projects_root
        self.vault_path = vault_path
        self.obsidian_folder = obsidian_folder

        self.handler = ProjectWatchHandler(
            projects_root=projects_root,
            vault_path=vault_path,
            obsidian_folder=obsidian_folder,
        )

        self.observer = Observer()
        self.observer.schedule(
            self.handler,
            str(projects_root),
            recursive=True,
        )

        self._stop_event = Event()
        self._reindex_thread: Thread | None = None

    def _do_reindex(self, project_names: list[str]):
        """Perform reindexing for specified projects."""
        logger.info(f"🔄 Reindexing projects: {', '.join(project_names)}")

        try:
            indexer = ProjectIndexer(
                vault_path=self.vault_path,
                obsidian_folder=self.obsidian_folder,
            )

            # Only index specified projects
            for project_name in project_names:
                project_path = self.projects_root / project_name
                if project_path.exists() and project_path.is_dir():
                    projects = indexer.scan_directory(project_path.parent)
                    matching = [p for p in projects if p.name == project_name]
                    if matching:
                        indexer.save_to_obsidian(matching[0])
                        logger.info(f"✅ Updated: {project_name}")

            logger.info(f"✨ Reindex complete for {len(project_names)} project(s)")

        except Exception as e:
            logger.error(f"❌ Reindex failed: {e}", exc_info=True)

    def _reindex_loop(self):
        """Background loop that performs reindexing when scheduled."""
        while not self._stop_event.is_set():
            now = datetime.now()

            # Find projects ready to reindex (debounced)
            ready_projects = [
                name
                for name, scheduled_time in self.handler._pending_projects.items()
                if now - scheduled_time >= timedelta(seconds=DEBOUNCE_SECONDS)
            ]

            if ready_projects:
                self._do_reindex(ready_projects)

                # Clear completed projects
                for name in ready_projects:
                    del self.handler._pending_projects[name]

            # Sleep briefly to avoid busy-waiting
            self._stop_event.wait(1)

    def start(self):
        """Start the watcher service."""
        logger.info("🚀 Starting Project Watcher service...")
        logger.info(f"📁 Watching: {self.projects_root}")
        logger.info(f"💾 Output: {self.vault_path / self.obsidian_folder}")
        logger.info(f"⏱️  Debounce: {DEBOUNCE_SECONDS}s")
        logger.info("Press Ctrl+C to stop\n")

        # Start file observer
        self.observer.start()

        # Start reindex loop
        self._reindex_thread = Thread(target=self._reindex_loop, daemon=True)
        self._reindex_thread.start()

        logger.info("✅ Watcher running. Changes will be auto-synced.\n")

        # Keep running until stopped
        try:
            while not self._stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """Stop the watcher service."""
        logger.info("\n⏹️  Stopping Project Watcher...")

        self._stop_event.set()
        self.observer.stop()

        if self._reindex_thread:
            self._reindex_thread.join(timeout=5)

        logger.info("👋 Watcher stopped.")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python -m clawdiney.scripts.watch_projects <projects_root>")
        print("Example: python -m clawdiney.scripts.watch_projects ~/Documentos/projetos")
        sys.exit(1)

    projects_root = Path(sys.argv[1]).expanduser().resolve()

    if not projects_root.exists():
        logger.error(f"Projects root does not exist: {projects_root}")
        sys.exit(1)

    if not projects_root.is_dir():
        logger.error(f"Projects root is not a directory: {projects_root}")
        sys.exit(1)

    # Default vault path
    vault_path = Path.home() / "Documents" / "ObsidianVault"

    if not vault_path.exists():
        logger.error(f"Obsidian vault not found: {vault_path}")
        sys.exit(1)

    # Start watcher
    service = WatcherService(
        projects_root=projects_root,
        vault_path=vault_path,
        obsidian_folder="00_Inbox/Projetos",
    )

    service.start()


if __name__ == "__main__":
    main()
