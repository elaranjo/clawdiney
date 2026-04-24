"""
Configuration for selective project indexing in Clawdiney.

Defines which files to index and which to ignore for optimal token usage.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class IndexConfig:
    """Configuration for project indexing."""

    # Patterns to include in indexing (glob patterns)
    include_patterns: list[str]
    # Patterns to exclude from indexing (glob patterns)
    exclude_patterns: list[str]
    # Maximum file size to index (in bytes)
    max_file_size: int = 100_000
    # Maximum depth to scan
    max_depth: int = 5


# Default configuration for all projects
DEFAULT_CONFIG = IndexConfig(
    include_patterns=[
        # Documentation
        "README.md",
        "README.*.md",
        "CLAUDE.md",
        "ARCHITECTURE.md",
        "docs/**/*.md",
        "documentation/**/*.md",
        # Configuration files
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements*.txt",
        "package.json",
        "package-lock.json",
        "tsconfig.json",
        "docker-compose.yml",
        "docker-compose.*.yml",
        "Dockerfile",
        ".env.example",
        # Entry points
        "main.py",
        "app.py",
        "index.js",
        "index.ts",
        "src/**/__init__.py",
        "src/**/main.py",
        "src/**/*.py",
        # Routes and APIs
        "**/routes/*.py",
        "**/api/*.py",
        "**/endpoints/*.py",
        "**/views/*.py",
        "**/controllers/*.ts",
        "**/routes/*.ts",
        # Models and schemas
        "**/models/*.py",
        "**/schemas/*.py",
        "**/types/*.ts",
        "**/interfaces/*.ts",
        # Database
        "**/migrations/*.py",
        "**/alembic/versions/*.py",
        "schema.prisma",
        "**/*.sql",
    ],
    exclude_patterns=[
        # Tests
        "**/tests/**",
        "**/test_*.py",
        "**/*_test.py",
        "**/*.test.js",
        "**/*.test.ts",
        "**/__tests__/**",
        "**/conftest.py",
        # Cache and build
        "**/__pycache__/**",
        "**/node_modules/**",
        "**/dist/**",
        "**/build/**",
        "**/coverage/**",
        "**/.pytest_cache/**",
        "**/.ruff_cache/**",
        "**/.mypy_cache/**",
        "**/.venv/**",
        "**/venv/**",
        "**/env/**",
        # Git and IDE
        "**/.git/**",
        "**/.github/**",
        "**/.vscode/**",
        "**/.idea/**",
        # Secrets and sensitive
        "**/.env",
        "**/.env.*",
        "**/*.pem",
        "**/*.key",
        "**/*secret*",
        "**/*credential*",
        # Generated and vendor
        "**/vendor/**",
        "**/target/**",
        "**/*.pyc",
        "**/*.pyo",
        "**/*.so",
        "**/*.dll",
        "**/*.min.js",
        "**/*.min.css",
        "**/lock.json",
        "**/*.lock",
    ],
)


# Project-specific overrides
PROJECT_CONFIGS: dict[str, IndexConfig] = {
    "clawdiney": IndexConfig(
        include_patterns=[
            "README.md",
            "CLAUDE.md",
            "pyproject.toml",
            "src/clawdiney/**/*.py",
            "docker/docker-compose.yml",
            "scripts/*.sh",
        ],
        exclude_patterns=[
            "**/tests/**",
            "**/conftest.py",
            "**/__pycache__/**",
            "**/*.pyc",
            "**/coverage/**",
        ],
    ),
}


def get_config_for_project(project_name: str) -> IndexConfig:
    """Get indexing configuration for a specific project."""
    return PROJECT_CONFIGS.get(project_name, DEFAULT_CONFIG)


def should_index_file(file_path: Path, project_name: Optional[str] = None) -> bool:
    """Determine if a file should be indexed based on configuration."""
    import fnmatch

    config = get_config_for_project(project_name or "")
    file_str = str(file_path)

    # Check exclusions first
    for pattern in config.exclude_patterns:
        if fnmatch.fnmatch(file_str, pattern):
            return False

    # Check inclusions
    for pattern in config.include_patterns:
        if fnmatch.fnmatch(file_str, pattern):
            # Check file size
            try:
                if file_path.stat().st_size > config.max_file_size:
                    return False
            except OSError:
                return False
            return True

    return False
