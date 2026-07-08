"""
Cross-encoder reranker for Clawdiney.

Wraps BAAI/bge-reranker-v2-m3 via sentence-transformers (optional extra:
pip install clawdiney[rerank]). The model is lazy-loaded on first use;
if sentence-transformers is missing or the model fails to load, reranking
degrades gracefully to a no-op (input order preserved).
"""

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "BAAI/bge-reranker-v2-m3"


class CrossEncoderReranker:
    """Lazy-loading cross-encoder reranker with graceful degradation."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name
        self._model: Any = None
        self._load_failed = False
        self._lock = threading.Lock()

    @property
    def available(self) -> bool:
        """True if the model is loaded or loadable (does not trigger load)."""
        return self._model is not None and not self._load_failed

    def _ensure_model(self) -> bool:
        if self._model is not None:
            return True
        if self._load_failed:
            return False
        with self._lock:
            if self._model is not None:
                return True
            if self._load_failed:
                return False
            try:
                from sentence_transformers import CrossEncoder

                logger.info("Loading cross-encoder model: %s", self.model_name)
                self._model = CrossEncoder(self.model_name)
                return True
            except ImportError:
                logger.warning(
                    "sentence-transformers not installed; reranking disabled. "
                    "Install with: pip install clawdiney[rerank]"
                )
                self._load_failed = True
                return False
            except Exception as exc:
                logger.warning(
                    "Failed to load cross-encoder '%s': %s; reranking disabled",
                    self.model_name,
                    exc,
                )
                self._load_failed = True
                return False

    def warm_up(self) -> bool:
        """Eagerly load the model (e.g., in a background thread at startup)."""
        return self._ensure_model()

    def rerank(
        self, query: str, results: list[tuple[str, dict[str, Any]]]
    ) -> list[tuple[str, dict[str, Any]]]:
        """
        Rerank (document, metadata) tuples by cross-encoder score, descending.
        Returns input unchanged when the model is unavailable or on error.
        """
        if len(results) < 2:
            return results
        if not self._ensure_model():
            return results
        try:
            pairs = [(query, doc) for doc, _meta in results]
            scores = self._model.predict(pairs)
            ranked = sorted(zip(scores, results), key=lambda x: x[0], reverse=True)
            return [item for _score, item in ranked]
        except Exception as exc:
            logger.warning("Rerank failed: %s; returning original order", exc)
            return results


# Process-wide singleton
_reranker_lock = threading.Lock()
_reranker_instance: CrossEncoderReranker | None = None


def get_reranker() -> CrossEncoderReranker:
    global _reranker_instance
    if _reranker_instance is None:
        with _reranker_lock:
            if _reranker_instance is None:
                _reranker_instance = CrossEncoderReranker()
    return _reranker_instance
