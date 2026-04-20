import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Centralized configuration class for Clawdiney"""

    # Paths
    VAULT_PATH = os.path.expanduser(os.getenv("VAULT_PATH", "~/Documents/ObsidianVault"))
    CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
    CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))

    # Model
    MODEL_NAME = os.getenv("MODEL_NAME", "bge-m3")

    # Neo4j
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

    @classmethod
    def get_chroma_client_config(cls):
        """Returns configuration for ChromaDB HTTP client"""
        return {
            "host": cls.CHROMA_HOST,
            "port": cls.CHROMA_PORT
        }