"""Cross-encoder reranker tests (mocked model)."""

from unittest.mock import MagicMock, patch

from clawdiney.reranker import CrossEncoderReranker, get_reranker, reset_reranker


def _results(n):
    return [(f"doc{i}", {"path": f"n{i}.md"}) for i in range(n)]


class TestRerank:
    def test_ordering_follows_scores(self):
        rr = CrossEncoderReranker()
        model = MagicMock()
        model.predict.return_value = [0.1, 0.9, 0.5]
        rr._model = model
        ranked = rr.rerank("q", _results(3))
        assert [meta["path"] for _d, meta in ranked] == ["n1.md", "n2.md", "n0.md"]

    def test_missing_dependency_falls_back(self, caplog):
        rr = CrossEncoderReranker()
        original = _results(3)
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            ranked = rr.rerank("q", original)
        assert ranked == original
        assert rr._load_failed

    def test_load_failure_warned_once_then_noop(self):
        rr = CrossEncoderReranker()
        rr._load_failed = True
        original = _results(2)
        assert rr.rerank("q", original) == original

    def test_predict_error_returns_original(self):
        rr = CrossEncoderReranker()
        model = MagicMock()
        model.predict.side_effect = RuntimeError("cuda oom")
        rr._model = model
        original = _results(2)
        assert rr.rerank("q", original) == original

    def test_short_input_skips_model(self):
        rr = CrossEncoderReranker()
        one = _results(1)
        assert rr.rerank("q", one) == one
        assert rr._model is None  # never loaded


class TestEngineIntegration:
    def test_disabled_by_config_loads_no_model(self, monkeypatch, tmp_path):
        from clawdiney.query_engine import BrainQueryEngine
        from clawdiney.storage import BrainStorage

        vault_root = tmp_path / "vault"
        vault_root.mkdir()
        monkeypatch.delenv("VAULTS_DIR", raising=False)
        monkeypatch.delenv("VAULTS", raising=False)
        monkeypatch.setattr("clawdiney.config.Config.VAULT_PATH", str(vault_root))
        monkeypatch.setattr("clawdiney.config.Config.ENABLE_RERANK", False)

        storage = BrainStorage(db_path=tmp_path / "brain.db", dimension=4)
        provider = MagicMock()
        provider.embed.return_value = [1.0, 2.0, 3.0, 4.0]

        engine = BrainQueryEngine(vault="default", storage=storage, provider=provider)
        with patch("clawdiney.query_engine.get_reranker") as get_rr:
            engine.query("anything", expand_graph=False)
            get_rr.assert_not_called()
        storage.close()


class TestConfigurableModel:
    def test_default_model_unchanged_when_unset(self, monkeypatch):
        reset_reranker()
        monkeypatch.delenv("RERANK_MODEL", raising=False)
        monkeypatch.setattr(
            "clawdiney.config.Config.RERANK_MODEL", "BAAI/bge-reranker-v2-m3"
        )
        rr = get_reranker()
        assert rr.model_name == "BAAI/bge-reranker-v2-m3"
        reset_reranker()

    def test_alternate_model_loads_when_configured(self, monkeypatch):
        reset_reranker()
        monkeypatch.setattr(
            "clawdiney.config.Config.RERANK_MODEL",
            "cross-encoder/ms-marco-MiniLM-L-6-v2",
        )
        rr = get_reranker()
        assert rr.model_name == "cross-encoder/ms-marco-MiniLM-L-6-v2"
        reset_reranker()

    def test_reranker_uses_configured_model_name_directly(self):
        rr = CrossEncoderReranker("some/other-model")
        assert rr.model_name == "some/other-model"
