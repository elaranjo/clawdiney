"""Tests for embedding providers (mocked ollama client)."""

import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from clawdiney.embedding_providers import (
    OllamaEmbeddingProvider,
    OpenAIEmbeddingProvider,
    default_provider,
    get_embedding_provider,
)


@pytest.fixture()
def provider():
    with patch("ollama.Client") as client_cls:
        prov = OllamaEmbeddingProvider(model_name="bge-m3")
        prov.mock_client = client_cls.return_value
        yield prov


class TestOllamaProvider:
    def test_embed_uses_embed_api(self, provider):
        provider.mock_client.embed.return_value = {"embeddings": [[0.1, 0.2]]}
        result = provider.embed("hello")
        provider.mock_client.embed.assert_called_once_with(
            model="bge-m3", input="hello", keep_alive="30m"
        )
        assert result == [0.1, 0.2]

    def test_embed_batch_single_native_call(self, provider):
        provider.mock_client.embed.return_value = {"embeddings": [[0.1], [0.2]]}
        result = provider.embed_batch(["a", "b"])
        provider.mock_client.embed.assert_called_once_with(
            model="bge-m3", input=["a", "b"], keep_alive="30m"
        )
        assert result == [[0.1], [0.2]]

    def test_embed_batch_empty(self, provider):
        assert provider.embed_batch([]) == []
        provider.mock_client.embed.assert_not_called()

    def test_retry_on_transient_connection_error(self, provider):
        provider.mock_client.embed.side_effect = [
            ConnectionError("boom"),
            {"embeddings": [[0.5]]},
        ]
        assert provider.embed("x") == [0.5]
        assert provider.mock_client.embed.call_count == 2


class TestFactory:
    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown provider"):
            get_embedding_provider("nope")

    def test_default_provider_is_ollama(self, monkeypatch):
        with patch("ollama.Client", MagicMock()):
            monkeypatch.setattr("clawdiney.config.Config.EMBEDDING_PROVIDER", "ollama")
            prov = default_provider()
            assert isinstance(prov, OllamaEmbeddingProvider)

    def test_default_provider_uses_configured_openai_model(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "test-key")
        client = MagicMock()
        monkeypatch.setitem(
            sys.modules, "openai", SimpleNamespace(OpenAI=lambda: client)
        )
        monkeypatch.setattr("clawdiney.config.Config.EMBEDDING_PROVIDER", "openai")
        monkeypatch.setattr(
            "clawdiney.config.Config.MODEL_NAME", "text-embedding-3-large"
        )

        provider = default_provider()
        assert isinstance(provider, OpenAIEmbeddingProvider)
        client.embeddings.create.return_value.data = [
            SimpleNamespace(index=1, embedding=[2.0]),
            SimpleNamespace(index=0, embedding=[1.0]),
        ]
        assert provider.embed_batch(["first", "second"]) == [[1.0], [2.0]]
        client.embeddings.create.assert_called_once_with(
            model="text-embedding-3-large", input=["first", "second"]
        )
        assert provider.embed_batch([]) == []

    def test_openai_requires_key(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            OpenAIEmbeddingProvider()
