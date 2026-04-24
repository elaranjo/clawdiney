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

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def main():
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

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Validate paths
    if not args.projects_root.exists():
        logger.error(f"Projects root does not exist: {args.projects_root}")
        sys.exit(1)

    if not args.vault.exists():
        logger.error(f"Obsidian vault does not exist: {args.vault}")
        sys.exit(1)

    logger.info(f"Scanning projects in: {args.projects_root}")
    logger.info(f"Output vault: {args.vault}")

    # Create indexer
    indexer = ProjectIndexer(vault_path=args.vault, obsidian_folder=args.folder)

    if args.dry_run:
        logger.info("DRY RUN - No files will be saved\n")
        projects = indexer.scan_directory(args.projects_root)

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

    else:
        logger.info("Indexing projects...")
        saved_paths = indexer.index_all(args.projects_root)

        print(f"\n✅ Indexed {len(indexer.projects)} projects")
        print("\nSaved documentation:")
        for path in saved_paths:
            print(f"  📄 {path}")

        print("\n💡 Tip: Run the Clawdiney indexer to make projects searchable")
        print("   python -m clawdiney.indexer")


if __name__ == "__main__":
    main()
