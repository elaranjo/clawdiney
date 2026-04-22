import os

import pytest

from query_engine import BrainQueryEngine

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_BRAIN_INTEGRATION") != "1",
    reason="Set RUN_BRAIN_INTEGRATION=1 to execute integration tests against real services.",
)


def test_query_returns_string():
    engine = BrainQueryEngine()
    try:
        result = engine.query("design system", use_rerank=False)
        assert isinstance(result, str)
    finally:
        engine.close()


def test_resolve_note_returns_list():
    engine = BrainQueryEngine()
    try:
        result = engine.resolve_note("README.md")
        assert isinstance(result, list)
    finally:
        engine.close()
