import logging
import os
from pathlib import Path

from dotenv import load_dotenv

from .constants import (
    CHUNK_OVERLAP_DEFAULT,
    CHUNK_SIZE_DEFAULT,
)
from .vault_config import VaultConfig, load_vault_config, validate_linked_vaults

logger = logging.getLogger(__name__)

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
    BRAIN_DB_PATH = os.path.expanduser(
        os.getenv("BRAIN_DB_PATH", "~/.clawdiney/brain.db")
    )

    @classmethod
    def _is_multi_vault(cls) -> bool:
        """Check if multi-vault mode is enabled via VAULTS or VAULTS_DIR env var."""
        return os.getenv("VAULTS") is not None or os.getenv("VAULTS_DIR") is not None

    @classmethod
    def _discover_vaults_from_dir(cls) -> dict[str, Path]:
        vaults_dir = os.getenv("VAULTS_DIR")
        if not vaults_dir:
            logger.warning("VAULTS_DIR is set but empty")
            return {}
        vaults_path = Path(vaults_dir).expanduser().resolve()
        if not vaults_path.is_dir():
            logger.warning("VAULTS_DIR '%s' is not a directory", vaults_dir)
            return {}
        discovered: dict[str, Path] = {}
        configs: dict[str, VaultConfig] = {}
        for entry in sorted(vaults_path.iterdir()):
            if not entry.is_dir():
                continue
            toml_path = entry / "clawdiney.toml"
            if not toml_path.exists():
                continue
            try:
                vc = load_vault_config(entry)
            except (ValueError, Exception) as exc:
                logger.warning("Skipping '%s': %s", entry.name, exc)
                continue
            if vc.id in discovered:
                logger.warning(
                    "Duplicate vault id '%s' in '%s', skipping", vc.id, entry.name
                )
                continue
            discovered[vc.id] = entry
            configs[vc.id] = vc
        if configs:
            try:
                validate_linked_vaults(configs)
            except ValueError as exc:
                logger.warning("linked_vaults validation failed: %s", exc)
                return {}
        return discovered

    @classmethod
    def get_vault_path(cls, vault_id: str) -> Path:
        if os.getenv("VAULTS_DIR"):
            vaults = cls._discover_vaults_from_dir()
            if vault_id in vaults:
                return vaults[vault_id]
            raise KeyError(
                f"Vault '{vault_id}' not found in VAULTS_DIR. "
                f"Available: {list(vaults.keys())}"
            )
        if cls._is_multi_vault():
            env_key = f"VAULT_{vault_id.upper()}_PATH"
            raw = os.getenv(env_key)
            if raw is None:
                raise KeyError(
                    f"Vault '{vault_id}' not configured. "
                    f"Set {env_key} in .env or environment."
                )
            return Path(os.path.expanduser(raw))
        return Path(cls.VAULT_PATH)

    @classmethod
    def get_all_vaults(cls) -> dict[str, Path]:
        vaults_dir = os.getenv("VAULTS_DIR")
        if vaults_dir:
            if os.getenv("VAULTS"):
                logger.warning("Both VAULTS and VAULTS_DIR are set. Using VAULTS_DIR.")
            return cls._discover_vaults_from_dir()
        if not cls._is_multi_vault():
            return {"default": Path(cls.VAULT_PATH)}
        vaults: dict[str, Path] = {}
        for vid in os.getenv("VAULTS", "").split(","):
            vid = vid.strip()
            if vid:
                vaults[vid] = cls.get_vault_path(vid)
        return vaults

    @classmethod
    def get_default_vault(cls) -> str:
        vaults_dir = os.getenv("VAULTS_DIR")
        if vaults_dir:
            vaults = cls._discover_vaults_from_dir()
            if not vaults:
                return "default"
            default = os.getenv("MCP_DEFAULT_VAULT")
            if default and default in vaults:
                return default
            return next(iter(vaults))
        if not cls._is_multi_vault():
            return "default"
        default = os.getenv("MCP_DEFAULT_VAULT")
        if default:
            return default
        first = os.getenv("VAULTS", "").split(",")[0].strip()
        return first or "default"

    # Model / embeddings
    MODEL_NAME = os.getenv("MODEL_NAME", "bge-m3")
    EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama")
    EMBEDDING_DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1024"))
    ENABLE_RERANK = _get_bool("ENABLE_RERANK", True)

    # Project knowledge graph
    CARD_LLM_MODEL = os.getenv("CARD_LLM_MODEL", "qwen3")
    ENTITY_RESOLUTION_THRESHOLD = float(
        os.getenv("ENTITY_RESOLUTION_THRESHOLD", "0.85")
    )

    # Memory auto-write (write_memory MCP tool)
    MEMORY_MIN_CONFIDENCE = float(os.getenv("MEMORY_MIN_CONFIDENCE", "0.3"))

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

        except Exception as e:
            warnings.append(f"Could not connect to Ollama: {e}")

        return warnings

    # Chunking
    CHUNKING_STRATEGY = os.getenv("CHUNKING_STRATEGY", "headers")
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", str(CHUNK_SIZE_DEFAULT)))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", str(CHUNK_OVERLAP_DEFAULT)))
