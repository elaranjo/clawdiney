"""Tests for the project_indexer module."""

import tempfile
from pathlib import Path

import pytest

from clawdiney.project_indexer import ProjectInfo, ProjectIndexer


class TestProjectIndexer:
    """Test cases for ProjectIndexer."""

    @pytest.fixture
    def temp_vault(self):
        """Create a temporary Obsidian vault."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    @pytest.fixture
    def temp_projects(self):
        """Create a temporary projects directory with test projects."""
        with tempfile.TemporaryDirectory() as tmpdir:
            projects_root = Path(tmpdir)

            # Create a Python project
            python_proj = projects_root / "test_python_project"
            python_proj.mkdir()
            (python_proj / "pyproject.toml").write_text("""
[project]
name = "test-project"
version = "1.0.0"
description = "A test project"
dependencies = ["fastapi>=0.100.0", "pydantic>=2.0"]

[project.scripts]
test-cmd = "test_project:main"
""")
            (python_proj / "main.py").write_text("print('hello')")
            (python_proj / "src").mkdir()
            (python_proj / "src" / "__init__.py").write_text("")

            # Create a Node.js project
            node_proj = projects_root / "test_node_project"
            node_proj.mkdir()
            (node_proj / "package.json").write_text("""
{
  "name": "test-node-project",
  "version": "2.0.0",
  "description": "A Node.js test project",
  "scripts": {
    "build": "tsc",
    "start": "node dist/index.js"
  },
  "dependencies": {
    "express": "^4.18.0",
    "typescript": "^5.0.0"
  },
  "devDependencies": {
    "jest": "^29.0.0"
  }
}
""")
            (node_proj / "index.js").write_text("console.log('hello')")

            yield projects_root

    def test_detect_python_project(self, temp_projects):
        """Test detection of Python projects."""
        indexer = ProjectIndexer(vault_path=tempfile.gettempdir())
        project_path = temp_projects / "test_python_project"

        project_type = indexer._detect_project_type(project_path)

        assert project_type == "python"

    def test_detect_node_project(self, temp_projects):
        """Test detection of Node.js projects."""
        indexer = ProjectIndexer(vault_path=tempfile.gettempdir())
        project_path = temp_projects / "test_node_project"

        project_type = indexer._detect_project_type(project_path)

        assert project_type == "node"

    def test_extract_python_info(self, temp_projects):
        """Test extraction of Python project information."""
        indexer = ProjectIndexer(vault_path=tempfile.gettempdir())
        project_path = temp_projects / "test_python_project"
        info = ProjectInfo(name="test", path=project_path)

        indexer._extract_python_info(project_path, info)

        assert info.language == "Python"
        assert info.version == "1.0.0"
        assert info.description == "A test project"
        assert "fastapi>=0.100.0" in info.dependencies
        assert "FastAPI" in info.stack
        assert "Pydantic" in info.stack
        assert "test-cmd" in info.scripts

    def test_extract_node_info(self, temp_projects):
        """Test extraction of Node.js project information."""
        indexer = ProjectIndexer(vault_path=tempfile.gettempdir())
        project_path = temp_projects / "test_node_project"
        info = ProjectInfo(name="test", path=project_path)

        indexer._extract_node_info(project_path, info)

        assert info.language == "Node.js"
        assert info.version == "2.0.0"
        assert "express" in info.dependencies
        assert "typescript" in info.dependencies
        assert "jest" in info.dev_dependencies
        assert "Express" in info.stack
        assert "TypeScript" in info.stack
        assert "build" in info.scripts
        assert "start" in info.scripts

    def test_extract_structure(self, temp_projects):
        """Test extraction of project structure."""
        indexer = ProjectIndexer(vault_path=tempfile.gettempdir())
        project_path = temp_projects / "test_python_project"
        info = ProjectInfo(name="test", path=project_path)

        indexer._extract_structure(project_path, info)

        assert len(info.structure) > 0
        assert any("src" in s for s in info.structure)
        assert any("main.py" in s for s in info.structure)
        # Should not include ignored directories
        assert not any("__pycache__" in s for s in info.structure)

    def test_extract_entry_points(self, temp_projects):
        """Test extraction of entry points."""
        indexer = ProjectIndexer(vault_path=tempfile.gettempdir())
        project_path = temp_projects / "test_python_project"
        info = ProjectInfo(name="test", path=project_path)

        indexer._extract_entry_points(project_path, info)

        assert "main.py" in info.entry_points
        assert "src/__init__.py" in info.entry_points

    def test_scan_directory(self, temp_projects):
        """Test scanning a directory for projects."""
        indexer = ProjectIndexer(vault_path=tempfile.gettempdir())

        projects = indexer.scan_directory(temp_projects)

        assert len(projects) == 2
        project_names = {p.name for p in projects}
        assert "test_python_project" in project_names
        assert "test_node_project" in project_names

    def test_generate_markdown(self, temp_projects):
        """Test Markdown generation."""
        indexer = ProjectIndexer(vault_path=tempfile.gettempdir())
        project_path = temp_projects / "test_python_project"
        info = ProjectInfo(name="test_python_project", path=project_path)
        indexer._extract_python_info(project_path, info)

        markdown = indexer.generate_markdown(info)

        assert "# test_python_project" in markdown
        assert "## Stack" in markdown
        assert "Python" in markdown
        assert "FastAPI" in markdown or "Frameworks" in markdown
        assert "test-cmd" in markdown

    def test_save_to_obsidian(self, temp_vault, temp_projects):
        """Test saving documentation to Obsidian."""
        indexer = ProjectIndexer(vault_path=temp_vault, obsidian_folder="Projetos")
        project_path = temp_projects / "test_python_project"
        info = ProjectInfo(name="test_python_project", path=project_path)
        indexer._extract_python_info(project_path, info)

        saved_path = indexer.save_to_obsidian(info)

        assert saved_path.exists()
        assert saved_path.suffix == ".md"
        assert saved_path.read_text().startswith("# test_python_project")

    def test_index_all(self, temp_vault, temp_projects):
        """Test indexing all projects."""
        indexer = ProjectIndexer(vault_path=temp_vault, obsidian_folder="Projetos")

        saved_paths = indexer.index_all(temp_projects)

        assert len(saved_paths) == 2
        for path in saved_paths:
            assert path.exists()
            assert path.suffix == ".md"

    def test_ignore_hidden_directories(self, temp_projects):
        """Test that hidden directories are ignored."""
        # Create a hidden project directory
        hidden_proj = temp_projects / ".hidden_project"
        hidden_proj.mkdir()
        (hidden_proj / "pyproject.toml").write_text("[project]\nname = 'hidden'")

        indexer = ProjectIndexer(vault_path=tempfile.gettempdir())
        projects = indexer.scan_directory(temp_projects)

        project_names = {p.name for p in projects}
        assert ".hidden_project" not in project_names

    def test_project_info_dataclass(self):
        """Test ProjectInfo dataclass defaults."""
        info = ProjectInfo(name="test", path=Path("/test"))

        assert info.name == "test"
        assert info.language == ""
        assert info.version == ""
        assert info.stack == []
        assert info.dependencies == []
        assert info.dev_dependencies == []
        assert info.scripts == {}
        assert info.structure == []
        assert info.entry_points == []
        assert info.description == ""
        assert info.repository == ""
        assert info.generated_at is not None
