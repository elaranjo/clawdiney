#!/usr/bin/env python3
"""
CLI script to index projects and generate documentation for Obsidian.

Usage:
    python -m clawdiney.scripts.index_projects [options]

Examples:
    # Index all projects in a directory
    python -m clawdiney.scripts.index_projects ~/Documentos/projetos

    # Index a specific project
    python -m clawdiney.scripts.index_projects ~/Documentos/projetos/meu-projeto

    # Dry run (preview only)
    python -m clawdiney.scripts.index_projects ~/Documentos/projetos --dry-run

    # Verbose output
    python -m clawdiney.scripts.index_projects ~/Documentos/projetos -v
"""

import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

from clawdiney.project_indexer import ProjectIndexer

# Load environment variables
load_dotenv()

# Setup logging with better formatting
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Index projects and generate documentation for Obsidian",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        "projects_root",
        type=Path,
        nargs="?",
        default=Path.home() / "Documentos" / "projetos",
        help="Root directory containing projects (default: ~/Documentos/projetos)",
    )

    parser.add_argument(
        "--vault",
        type=Path,
        default=Path.home() / "Documents" / "ObsidianVault",
        help="Path to Obsidian vault (default: ~/Documents/ObsidianVault)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be indexed without saving",
    )

    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    parser.add_argument(
        "--folder",
        type=str,
        default="00_Inbox/Projetos",
        help="Obsidian folder for project docs (default: 00_Inbox/Projetos)",
    )

    return parser.parse_args()


def validate_paths(projects_root: Path, vault: Path) -> bool:
    """Validate input and output paths.

    Args:
        projects_root: Root directory containing projects.
        vault: Obsidian vault path.

    Returns:
        True if valid, False otherwise.
    """
    # Security: Resolve and validate paths
    try:
        resolved_root = projects_root.resolve(strict=True)
    except (OSError, RuntimeError) as e:
        logger.error(f"Invalid projects root: {e}")
        return False

    if not resolved_root.is_dir():
        logger.error(f"Projects root is not a directory: {resolved_root}")
        return False

    try:
        resolved_vault = vault.resolve(strict=True)
    except (OSError, RuntimeError) as e:
        logger.error(f"Invalid vault path: {e}")
        return False

    if not resolved_vault.is_dir():
        logger.error(f"Vault is not a directory: {resolved_vault}")
        return False

    # Security: Prevent path traversal between vault and projects
    if str(resolved_vault).startswith(str(resolved_root)):
        logger.warning(
            "Vault is inside projects directory - this may cause recursive indexing"
        )

    return True


def run_dry_run(indexer: ProjectIndexer, projects_root: Path) -> None:
    """Run indexer in dry-run mode.

    Args:
        indexer: ProjectIndexer instance.
        projects_root: Root directory containing projects.
    """
    logger.info("DRY RUN - No files will be saved\n")
    projects = indexer.scan_directory(projects_root)

    for project in projects:
        print(f"\n📁 {project.name}")
        print(f"   Path: {project.path}")
        print(f"   Language: {project.language or 'Unknown'}")
        print(f"   Stack: {', '.join(project.stack) or 'None detected'}")
        print(f"   Dependencies: {len(project.dependencies)}")
        print(f"   Scripts: {len(project.scripts)}")
        print(f"   Entry points: {', '.join(project.entry_points) or 'None'}")

    print(f"\n\nTotal projects found: {len(projects)}")
    print("To save documentation, run without --dry-run")


def run_indexing(indexer: ProjectIndexer, projects_root: Path) -> int:
    """Run the indexer and save documentation.

    Args:
        indexer: ProjectIndexer instance.
        projects_root: Root directory containing projects.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    logger.info("Indexing projects...")
    saved_paths = indexer.index_all(projects_root)

    print(f"\n✅ Indexed {len(indexer.projects)} projects")
    print("\nSaved documentation:")
    for path in saved_paths:
        print(f"  📄 {path}")

    print("\n💡 Tip: Run the Clawdiney indexer to make projects searchable")
    print("   python -m clawdiney.indexer")

    return 0


def main() -> int:
    """Main entry point.

    Returns:
        Exit code (0 for success, 1 for error).
    """
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate paths
    if not validate_paths(args.projects_root, args.vault):
        return 1

    logger.info(f"Scanning projects in: {args.projects_root}")
    logger.info(f"Output vault: {args.vault}")

    try:
        # Create indexer
        indexer = ProjectIndexer(
            vault_path=args.vault, obsidian_folder=args.folder
        )
    except ValueError as e:
        logger.error(f"Failed to initialize indexer: {e}")
        return 1

    if args.dry_run:
        run_dry_run(indexer, args.projects_root)
    else:
        return run_indexing(indexer, args.projects_root)

    return 0


if __name__ == "__main__":
    sys.exit(main())
