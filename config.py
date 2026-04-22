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
    RERANK_MODEL_NAME = os.getenv("RERANK_MODEL_NAME", "")
    RERANK_THRESHOLD = os.getenv("RERANK_THRESHOLD", str(RERANK_THRESHOLD_DEFAULT))
    ENABLE_RERANK = _get_bool("ENABLE_RERANK", True)

    @classmethod
    def validate_ollama_models(cls) -> list[str]:
        """
        Validate that required Ollama models are available.
        Returns list of warning messages (empty if all OK).
        """
        warnings = []

        try:
            import ollama
            client = ollama.Client()
            available_models = client.list()
            model_names = [m["name"] for m in available_models.get("models", [])]

            # Check embedding model
            if cls.MODEL_NAME not in model_names:
                warnings.append(
                    f"Embedding model '{cls.MODEL_NAME}' not found in Ollama. "
                    f"Run: ollama pull {cls.MODEL_NAME}"
                )

            # Check rerank model (only if configured)
            if cls.ENABLE_RERANK and cls.RERANK_MODEL_NAME:
                if cls.RERANK_MODEL_NAME not in model_names:
                    warnings.append(
                        f"Rerank model '{cls.RERANK_MODEL_NAME}' not found in Ollama. "
                        f"Run: ollama pull {cls.RERANK_MODEL_NAME} "
                        f"or set ENABLE_RERANK=false to disable reranking"
                    )

        except Exception as e:
            warnings.append(f"Could not connect to Ollama: {e}")

        return warnings

    # Chunking
    CHUNKING_STRATEGY = os.getenv("CHUNKING_STRATEGY", "headers")
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", str(CHUNK_SIZE_DEFAULT)))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", str(CHUNK_OVERLAP_DEFAULT)))

    # Neo4j
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")

    @staticmethod
    def _validate_password_strength(password: str) -> None:
        """Validate Neo4j password strength with complexity requirements."""
        import re

        if len(password) < 12:
            raise ValueError("Neo4j password must be at least 12 characters long.")
        if not re.search(r"[A-Z]", password):
            raise ValueError(
                "Neo4j password must contain at least one uppercase letter."
            )
        if not re.search(r"[a-z]", password):
            raise ValueError(
                "Neo4j password must contain at least one lowercase letter."
            )
        if not re.search(r"\d", password):
            raise ValueError("Neo4j password must contain at least one digit.")

    @classmethod
    def get_neo4j_password(cls) -> str | None:
        """Get Neo4j password, allowing missing value during tests."""
        password = os.getenv("NEO4J_PASSWORD")
        if password is None and "PYTEST_CURRENT_TEST" not in os.environ:
            raise ValueError(
                "Neo4j password is required. Set NEO4J_PASSWORD in .env or environment."
            )
        if password and "PYTEST_CURRENT_TEST" not in os.environ:
            cls._validate_password_strength(password)
        return password

    @classmethod
    def get_chroma_client_config(cls) -> dict[str, Any]:
        """Returns configuration for ChromaDB HTTP client"""
        return {"host": cls.CHROMA_HOST, "port": cls.CHROMA_PORT}
