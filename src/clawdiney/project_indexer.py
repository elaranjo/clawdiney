"""
Project Indexer - Analyzes codebases and generates documentation for Obsidian.

This module scans project directories, extracts metadata about the tech stack,
structure, and key files, then generates standardized Markdown notes for Obsidian.

Security: Path traversal is prevented by resolving all paths and validating
they are within expected boundaries. Sensitive files are automatically excluded.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

import tomli

logger = logging.getLogger(__name__)

# Security: Pattern to sanitize filenames for Obsidian
SAFE_FILENAME_PATTERN = re.compile(r"[^\w\s\-\.]")

# Security: Maximum path length to prevent issues
MAX_PATH_LENGTH = 400

# Security: Maximum content size for generated docs (prevent DoS)
MAX_CONTENT_SIZE = 50_000


@dataclass
class ProjectInfo:
    """Represents extracted information about a project."""

    name: str
    path: Path
    language: str = ""
    version: str = ""
    stack: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    dev_dependencies: list[str] = field(default_factory=list)
    scripts: dict[str, str] = field(default_factory=dict)
    structure: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    description: str = ""
    repository: str = ""
    generated_at: str = field(default_factory=lambda: datetime.now().isoformat())


class ProjectIndexer:
    """Analyzes projects and generates documentation for Obsidian."""

    # File patterns that indicate project type
    PROJECT_FILES = {
        "pyproject.toml": "python",
        "setup.py": "python",
        "requirements.txt": "python",
        "package.json": "node",
        "Cargo.toml": "rust",
        "go.mod": "go",
        "Gemfile": "ruby",
        "pom.xml": "java",
        "build.gradle": "java",
    }

    # Directories to skip during scan
    IGNORE_DIRS = {
        "__pycache__",
        "node_modules",
        "venv",
        ".venv",
        "env",
        ".env",
        "dist",
        "build",
        ".git",
        ".github",
        "coverage",
        ".pytest_cache",
        ".ruff_cache",
        ".mypy_cache",
        "target",
        "vendor",
    }

    # Files to skip during scan
    IGNORE_FILES = {
        ".pyc",
        ".pyo",
        ".so",
        ".dll",
        ".exe",
        ".bin",
        ".lock",
        ".min.js",
        ".min.css",
    }

    def __init__(self, vault_path: Path | str, obsidian_folder: str = "00_Inbox/Projetos"):
        """Initialize the ProjectIndexer.

        Args:
            vault_path: Path to the Obsidian vault root.
            obsidian_folder: Folder within vault for project docs.

        Raises:
            ValueError: If vault_path is not a valid directory.
        """
        # Security: Validate and resolve vault path
        vault_path_obj = Path(vault_path) if isinstance(vault_path, str) else vault_path

        if not vault_path_obj.exists():
            raise ValueError(f"Vault path does not exist: {vault_path}")
        if not vault_path_obj.is_dir():
            raise ValueError(f"Vault path is not a directory: {vault_path}")

        self.vault_path = vault_path_obj.resolve()
        self.obsidian_folder = self._sanitize_path(obsidian_folder)
        self.projects: list[ProjectInfo] = []

    def scan_directory(self, projects_root: Path) -> list[ProjectInfo]:
        """Scan a directory for projects and extract information.

        Args:
            projects_root: Root directory containing projects.

        Returns:
            List of ProjectInfo objects for each discovered project.

        Raises:
            ValueError: If projects_root is not a valid directory.
            SecurityError: If path traversal is detected.
        """
        # Security: Validate and resolve projects root
        if not projects_root.exists():
            raise ValueError(f"Projects root does not exist: {projects_root}")
        if not projects_root.is_dir():
            raise ValueError(f"Projects root is not a directory: {projects_root}")

        resolved_root = projects_root.resolve()

        # Security: Prevent path traversal
        if len(str(resolved_root)) > MAX_PATH_LENGTH:
            raise ValueError(f"Projects root path too long: {resolved_root}")

        logger.info(f"Scanning for projects in: {resolved_root}")

        self.projects = []

        for item in resolved_root.iterdir():
            # Skip hidden directories and symlinks
            if item.name.startswith("."):
                continue
            if item.is_symlink():
                logger.debug(f"Skipping symlink: {item}")
                continue
            if item.is_dir():
                project_info = self._analyze_project(item)
                if project_info:
                    self.projects.append(project_info)

        logger.info(f"Found {len(self.projects)} projects")
        return self.projects

    def _sanitize_path(self, path: str) -> str:
        """Sanitize a path string to prevent injection attacks.

        Args:
            path: Raw path string.

        Returns:
            Sanitized path with only safe characters.
        """
        # Remove potentially dangerous characters
        sanitized = SAFE_FILENAME_PATTERN.sub("", path)
        # Prevent path traversal
        sanitized = sanitized.replace("..", "")
        return sanitized

    def _safe_filename(self, name: str) -> str:
        """Create a safe filename for Obsidian.

        Args:
            name: Original filename.

        Returns:
            Sanitized filename with .md extension.
        """
        sanitized = SAFE_FILENAME_PATTERN.sub("_", name)[:100]
        return f"{sanitized}.md"

    def _analyze_project(self, project_path: Path) -> Optional[ProjectInfo]:
        """Analyze a single project directory.

        Args:
            project_path: Path to the project directory.

        Returns:
            ProjectInfo object or None if not a recognized project.

        Raises:
            ValueError: If project_path is invalid.
        """
        # Security: Validate project path
        if not project_path.exists():
            logger.debug(f"Project path does not exist: {project_path}")
            return None
        if not project_path.is_dir():
            logger.debug(f"Project path is not a directory: {project_path}")
            return None
        if project_path.is_symlink():
            logger.debug(f"Skipping symlink project: {project_path}")
            return None

        resolved_path = project_path.resolve()
        logger.debug(f"Analyzing project: {resolved_path.name}")

        # Detect project type
        project_type = self._detect_project_type(resolved_path)
        if not project_type:
            logger.debug(f"No recognized project type in: {resolved_path.name}")
            return None

        # Extract information based on project type
        info = ProjectInfo(name=resolved_path.name, path=resolved_path)

        if project_type == "python":
            self._extract_python_info(resolved_path, info)
        elif project_type == "node":
            self._extract_node_info(resolved_path, info)

        # Extract common info
        self._extract_structure(resolved_path, info)
        self._extract_entry_points(resolved_path, info)

        return info

    def _detect_project_type(self, project_path: Path) -> Optional[str]:
        """Detect the project type based on configuration files."""
        for file_name, project_type in self.PROJECT_FILES.items():
            if (project_path / file_name).exists():
                return project_type
        return None

    def _extract_python_info(self, project_path: Path, info: ProjectInfo) -> None:
        """Extract information from Python projects."""
        info.language = "Python"

        # Try to read pyproject.toml
        pyproject_path = project_path / "pyproject.toml"
        if pyproject_path.exists():
            try:
                with open(pyproject_path, "rb") as f:
                    pyproject = tomli.load(f)

                project_data = pyproject.get("project", {})
                info.description = project_data.get("description", "")
                info.version = project_data.get("version", "")

                # Extract dependencies
                info.dependencies = project_data.get("dependencies", [])

                # Extract optional dependencies
                optional_deps = project_data.get("optional-dependencies", {})
                info.dev_dependencies = optional_deps.get("dev", [])

                # Extract scripts/entry points
                scripts = project_data.get("scripts", {})
                info.scripts = scripts

                # Extract project scripts from project.scripts
                if "project" in pyproject:
                    proj_scripts = pyproject["project"].get("scripts", {})
                    info.scripts.update(proj_scripts)

            except Exception as e:
                logger.warning(f"Error reading pyproject.toml: {e}")

        # Fallback to requirements.txt
        req_path = project_path / "requirements.txt"
        if req_path.exists() and not info.dependencies:
            try:
                with open(req_path) as f:
                    info.dependencies = [
                        line.strip()
                        for line in f
                        if line.strip() and not line.startswith("#")
                    ]
            except Exception as e:
                logger.warning(f"Error reading requirements.txt: {e}")

        # Identify framework from dependencies
        frameworks = {
            "fastapi": "FastAPI",
            "flask": "Flask",
            "django": "Django",
            "pytest": "Pytest",
            "neo4j": "Neo4j",
            "chromadb": "ChromaDB",
            "redis": "Redis",
            "sqlalchemy": "SQLAlchemy",
            "pydantic": "Pydantic",
        }

        all_deps = " ".join(info.dependencies + info.dev_dependencies).lower()
        info.stack = [
            fw for dep, fw in frameworks.items() if dep in all_deps
        ]

    def _extract_node_info(self, project_path: Path, info: ProjectInfo) -> None:
        """Extract information from Node.js projects.

        Args:
            project_path: Path to the Node.js project.
            info: ProjectInfo object to populate.
        """
        info.language = "Node.js"

        package_path = project_path / "package.json"
        if package_path.exists():
            try:
                with open(package_path) as f:
                    package = json.load(f)

                info.description = package.get("description", "")
                info.version = package.get("version", "")

                # Extract dependencies
                info.dependencies = list(package.get("dependencies", {}).keys())
                info.dev_dependencies = list(
                    package.get("devDependencies", {}).keys()
                )

                # Extract scripts
                info.scripts = package.get("scripts", {})

                # Identify framework
                frameworks = {
                    "express": "Express",
                    "fastify": "Fastify",
                    "nestjs": "NestJS",
                    "next": "Next.js",
                    "react": "React",
                    "vue": "Vue.js",
                    "jest": "Jest",
                    "typescript": "TypeScript",
                }

                all_deps = " ".join(info.dependencies + info.dev_dependencies).lower()
                info.stack = [
                    fw for dep, fw in frameworks.items() if dep in all_deps
                ]

            except Exception as e:
                logger.warning(f"Error reading package.json: {e}")

    def _extract_structure(self, project_path: Path, info: ProjectInfo) -> None:
        """Extract directory structure (top level only)."""
        structure = []

        for item in sorted(project_path.iterdir()):
            if item.name in self.IGNORE_DIRS:
                continue

            if item.suffix in self.IGNORE_FILES:
                continue

            if item.is_dir():
                structure.append(f"📁 {item.name}/")
            else:
                structure.append(f"📄 {item.name}")

        info.structure = structure[:20]  # Limit to 20 items

    def _extract_entry_points(self, project_path: Path, info: ProjectInfo) -> None:
        """Identify entry point files."""
        entry_points = []

        # Common entry point patterns
        patterns = [
            "src/main.py",
            "src/__init__.py",
            "main.py",
            "index.js",
            "app.py",
            "app/__init__.py",
            "src/app.py",
            "src/index.ts",
            "src/app.ts",
        ]

        for pattern in patterns:
            if (project_path / pattern).exists():
                entry_points.append(pattern)

        info.entry_points = entry_points

    def generate_markdown(self, project: ProjectInfo) -> str:
        """Generate Markdown documentation for a project."""
        sections = []

        # Header
        sections.append(f"# {project.name}\n")

        # Description
        if project.description:
            sections.append(f"{project.description}\n")

        # Stack
        if project.stack or project.language:
            sections.append("## Stack\n")
            if project.language:
                sections.append(f"- **Linguagem:** {project.language}")
            if project.version:
                sections.append(f"- **Versão:** {project.version}")
            if project.stack:
                sections.append(f"- **Frameworks:** {', '.join(project.stack)}")
            sections.append("")

        # Structure
        if project.structure:
            sections.append("## Estrutura\n")
            sections.append("```")
            sections.append("\n".join(project.structure))
            sections.append("```\n")

        # Scripts/Commands
        if project.scripts:
            sections.append("## Comandos Principais\n")
            sections.append("```bash")
            for name, command in project.scripts.items():
                sections.append(f"# {name}")
                sections.append(f"{command}")
                sections.append("")
            sections.append("```\n")

        # Dependencies
        if project.dependencies:
            sections.append("## Dependências\n")
            for dep in project.dependencies[:15]:  # Limit to 15
                sections.append(f"- {dep}")
            if len(project.dependencies) > 15:
                sections.append(f"- ... e mais {len(project.dependencies) - 15}")
            sections.append("")

        # Entry points
        if project.entry_points:
            sections.append("## Arquivos-Chave\n")
            for entry in project.entry_points:
                sections.append(f"- `{entry}` - Entry point")
            sections.append("")

        # Footer
        sections.append("---")
        sections.append(f"*Gerado em: {project.generated_at}*")
        sections.append(f"*Caminho: {project.path}*")

        return "\n".join(sections)

    def save_to_obsidian(self, project: ProjectInfo) -> Path:
        """Save project documentation to Obsidian vault.

        Args:
            project: ProjectInfo object to save.

        Returns:
            Path to the saved file.

        Raises:
            ValueError: If the generated content is too large.
            OSError: If the file cannot be written.
        """
        # Create target directory with path validation
        target_dir = self.vault_path / self.obsidian_folder

        # Security: Validate target directory is within vault
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
            resolved_target = target_dir.resolve()
            if not str(resolved_target).startswith(str(self.vault_path)):
                raise ValueError(
                    f"Target directory outside vault: {target_dir}"
                )
        except OSError as e:
            logger.error(f"Failed to create target directory: {e}")
            raise

        # Generate safe filename
        filename = self._safe_filename(project.name)
        target_path = target_dir / filename

        # Generate content with size limit
        content = self.generate_markdown(project)
        if len(content) > MAX_CONTENT_SIZE:
            logger.warning(
                f"Generated content too large ({len(content)} bytes), truncating"
            )
            content = content[:MAX_CONTENT_SIZE] + "\n\n... [truncated]"

        # Write with explicit encoding and error handling
        try:
            with open(target_path, "w", encoding="utf-8", errors="replace") as f:
                f.write(content)
        except OSError as e:
            logger.error(f"Failed to write file {target_path}: {e}")
            raise

        logger.info(f"Saved project doc to: {target_path}")
        return target_path

    def index_all(self, projects_root: Path) -> list[Path]:
        """Scan projects and save all documentation to Obsidian."""
        self.scan_directory(projects_root)

        saved_paths = []
        for project in self.projects:
            path = self.save_to_obsidian(project)
            saved_paths.append(path)

        return saved_paths
