import os
from typing import Any

from dotenv import load_dotenv

from constants import (
    CHUNK_OVERLAP_DEFAULT,
    CHUNK_SIZE_DEFAULT,
    RERANK_THRESHOLD_DEFAULT,
)

# Load environment variables from .env file
load_dotenv()


def _get_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _require_env(
    name: str, description: str | None = None, allow_test_mode: bool = True
) -> str | None:
    """
    Require an environment variable, raising ValueError if not set.

    Args:
        name: Environment variable name
        description: Human-readable description for error message
        allow_test_mode: If True, allow missing value when running under pytest
    """
    value = os.getenv(name)
    if value is None:
        # Allow missing values during testing (mocks will handle it)
        if allow_test_mode and (
            "pytest" in globals() or "PYTEST_CURRENT_TEST" in os.environ
        ):
            return None
        desc = description or name
        raise ValueError(f"{desc} is required. Set {name} in .env or environment.")
    return value


class Config:
    """Centralized configuration class for Clawdiney"""

    # Paths
    VAULT_PATH = os.path.expanduser(
        os.getenv("VAULT_PATH", "~/Documents/ObsidianVault")
    )
    CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
    CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))

    # Model
    MODEL_NAME = os.getenv("MODEL_NAME", "bge-m3")
    RERANK_MODEL_NAME = os.getenv(
        "RERANK_MODEL_NAME", "cross-encoder/ms-marco-MiniLM-L-6-v2"
    )
    RERANK_THRESHOLD = os.getenv("RERANK_THRESHOLD", str(RERANK_THRESHOLD_DEFAULT))
    ENABLE_RERANK = _get_bool("ENABLE_RERANK", True)

    # Chunking
    CHUNKING_STRATEGY = os.getenv("CHUNKING_STRATEGY", "headers")
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", str(CHUNK_SIZE_DEFAULT)))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", str(CHUNK_OVERLAP_DEFAULT)))

    # Neo4j
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")

    @classmethod
    def get_neo4j_password(cls) -> str | None:
        """Get Neo4j password, allowing missing value during tests."""
        password = os.getenv("NEO4J_PASSWORD")
        if password is None and "PYTEST_CURRENT_TEST" not in os.environ:
            raise ValueError(
                "Neo4j password is required. Set NEO4J_PASSWORD in .env or environment."
            )
        return password

    @classmethod
    def get_chroma_client_config(cls) -> dict[str, Any]:
        """Returns configuration for ChromaDB HTTP client"""
        return {"host": cls.CHROMA_HOST, "port": cls.CHROMA_PORT}
