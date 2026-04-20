"""
Example of using BrainEngine with context manager

This example demonstrates how to use the BrainEngine with context manager
support for automatic resource cleanup.
"""

from brain_mcp_server import BrainEngine

def example_with_context_manager():
    """Example using BrainEngine with context manager"""
    print("=== BrainEngine Context Manager Example ===")

    # Using BrainEngine with context manager
    # Connections are automatically closed when exiting the 'with' block
    with BrainEngine() as engine:
        # Perform search operations
        result = engine.search("example query")
        print(f"Search result: {result}")

        # Get related notes
        related = engine.get_related_notes("example_note")
        print(f"Related notes: {related}")

    print("Connections automatically closed!")

def example_without_context_manager():
    """Example using BrainEngine without context manager"""
    print("\n=== BrainEngine Manual Management Example ===")

    # Traditional usage - remember to call close()
    engine = BrainEngine()
    try:
        result = engine.search("example query")
        print(f"Search result: {result}")
    finally:
        # Must manually close connections
        engine.close()
        print("Connections manually closed!")

if __name__ == "__main__":
    # Run both examples
    example_with_context_manager()
    example_without_context_manager()