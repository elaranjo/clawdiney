"""
Examples for canonical path resolution and chunk inspection.
"""

from query_engine import BrainQueryEngine


def example_resolve_and_chunk():
    engine = BrainQueryEngine()
    try:
        print("=== resolve_note ===")
        candidates = engine.resolve_note("design.md")
        for candidate in candidates:
            print("-", candidate["path"])

        if candidates:
            canonical_path = candidates[0]["path"]
            print(f"\n=== get_note_chunks({canonical_path}) ===")
            for chunk in engine.get_note_chunks(canonical_path):
                print(f"- [{chunk['chunk_index']}] {chunk['header']}")
    finally:
        engine.close()


def example_direct_read():
    engine = BrainQueryEngine()
    try:
        candidates = engine.resolve_note("README.md")
        if not candidates:
            print("README.md not found in the configured vault.")
            return

        note = engine.get_note_by_path(candidates[0]["path"])
        print(f"\n=== get_note_by_path({note['path']}) ===")
        print(note["content"][:200] + "..." if len(note["content"]) > 200 else note["content"])
    finally:
        engine.close()


if __name__ == "__main__":
    example_resolve_and_chunk()
    example_direct_read()
