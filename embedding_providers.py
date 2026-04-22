"""
Embedding provider strategy pattern for Clawdiney.

This module defines the protocol for embedding providers and provides
implementations for Ollama, OpenAI, and other embedding services.
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for embedding providers."""

    def embed(self, text: str) -> list[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Input text to embed

        Returns:
            List of floats representing the embedding vector
        """
        ...

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """
        Generate embeddings for multiple texts.

        Args:
            texts: List of input texts to embed

        Returns:
            List of embedding vectors
        """
        ...


class OllamaEmbeddingProvider:
    """
    Ollama implementation of EmbeddingProvider.

    Uses local Ollama server for generating embeddings.
    """

    def __init__(self, model_name: str, timeout: int = 600):
        """
        Initialize Ollama embedding provider.

        Args:
            model_name: Name of the Ollama embedding model (e.g., 'bge-m3')
            timeout: Request timeout in seconds
        """
        import ollama

        self.model_name = model_name
        self.ollama_client = ollama.Client(timeout=timeout)

    def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        response = self.ollama_client.embeddings(
            model=self.model_name, prompt=text
        )
        return response["embedding"]

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts sequentially."""
        return [self.embed(text) for text in texts]


class OpenAIEmbeddingProvider:
    """
    OpenAI implementation of EmbeddingProvider.

    Uses OpenAI API for generating embeddings.
    Requires OPENAI_API_KEY environment variable.
    """

    def __init__(self, model_name: str = "text-embedding-3-small"):
        """
        Initialize OpenAI embedding provider.

        Args:
            model_name: Name of the OpenAI embedding model
        """
        from openai import OpenAI

        self.client = OpenAI()
        self.model_name = model_name

    def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text."""
        response = self.client.embeddings.create(
            model=self.model_name, input=text
        )
        return response.data[0].embedding

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts in batch."""
        response = self.client.embeddings.create(
            model=self.model_name, input=texts
        )
        return [item.embedding for item in response.data]


def get_embedding_provider(provider: str, **kwargs) -> EmbeddingProvider:
    """
    Factory function to get an embedding provider.

    Args:
        provider: Provider name ('ollama', 'openai')
        **kwargs: Provider-specific arguments

    Returns:
        Configured EmbeddingProvider instance

    Raises:
        ValueError: If provider name is not recognized
    """
    providers = {
        "ollama": OllamaEmbeddingProvider,
        "openai": OpenAIEmbeddingProvider,
    }

    if provider not in providers:
        available = ", ".join(providers.keys())
        raise ValueError(
            f"Unknown provider: {provider}. Available: {available}"
        )

    return providers[provider](**kwargs)
