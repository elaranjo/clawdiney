"""
Example of using BrainQueryEngine directly.

This replaces the old BrainEngine example and keeps the usage aligned with the
current core API.
"""

from query_engine import BrainQueryEngine


def example_query():
    engine = BrainQueryEngine()
    try:
        result = engine.query("design system", use_rerank=False)
        print("=== search_brain style query ===")
        print(result[:500])
    finally:
        engine.close()


def example_resolution():
    engine = BrainQueryEngine()
    try:
        print("\n=== resolve_note example ===")
        for candidate in engine.resolve_note("design.md"):
            print("-", candidate["path"])
    finally:
        engine.close()


if __name__ == "__main__":
    example_query()
    example_resolution()
