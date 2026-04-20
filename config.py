import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Centralized configuration class for Clawdiney"""

    # Paths
    VAULT_PATH = os.path.expanduser(os.getenv("VAULT_PATH", "~/Documents/ObsidianVault"))
    CHROMA_PATH = os.path.expanduser(os.getenv("CHROMA_PATH", "~/.clawdiney/chroma_db"))
    CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
    CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))

    # Model
    MODEL_NAME = os.getenv("MODEL_NAME", "bge-m3")

    # Neo4j
    NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

    # ChromaDB Client Type
    CHROMA_CLIENT_TYPE = os.getenv("CHROMA_CLIENT_TYPE", "persistent")  # persistent or http

    @classmethod
    def get_chroma_client_config(cls):
        """Returns configuration for ChromaDB client based on environment"""
        if cls.CHROMA_CLIENT_TYPE == "http":
            return {
                "type": "http",
                "host": cls.CHROMA_HOST,
                "port": cls.CHROMA_PORT
            }
        else:
            return {
                "type": "persistent",
                "path": cls.CHROMA_PATH
            }