"""
Example of using read_note with multiple file matches

This example demonstrates how the improved read_note method handles
ambiguous file names by listing all candidates.
"""

from brain_mcp_server import BrainEngine
from pathlib import Path
from config import Config

def setup_test_files():
    """Setup some test files for demonstration"""
    vault_path = Path(Config.VAULT_PATH)

    # Create test directory structure
    test_dirs = [
        vault_path / "frontend",
        vault_path / "backend",
        vault_path / "mobile"
    ]

    for dir_path in test_dirs:
        dir_path.mkdir(exist_ok=True)

        # Create a test file in each directory
        test_file = dir_path / "design.md"
        test_file.write_text(f"# {dir_path.name.title()} Design\n\nThis is the {dir_path.name} design document.")

def example_ambiguous_file_resolution():
    """Example showing how read_note handles ambiguous file names"""
    print("=== Ambiguous File Resolution Example ===")

    # Initialize BrainEngine
    engine = BrainEngine()

    try:
        # Try to read a file that exists in multiple locations
        result = engine.read_note("design.md")
        print("Reading 'design.md':")
        print(result)
        print()

        # Try to read a file that exists in only one location
        result = engine.read_note("README.md")  # Assuming this exists
        if "Multiple files found" not in result and "not found" not in result:
            print("Reading 'README.md':")
            print(result[:200] + "..." if len(result) > 200 else result)
            print()

    finally:
        engine.close()

def example_specific_file_reading():
    """Example showing how to read a specific file"""
    print("=== Specific File Reading Example ===")

    # If you know the specific file path, you can read it directly
    # This would typically be done by specifying the full path or
    # by selecting from the candidates list

    vault_path = Path(Config.VAULT_PATH)
    specific_file = vault_path / "frontend" / "design.md"

    if specific_file.exists():
        content = specific_file.read_text()
        print(f"Reading specific file {specific_file}:")
        print(content[:200] + "..." if len(content) > 200 else content)

if __name__ == "__main__":
    # Note: This example assumes you have a vault setup
    # Uncomment the following line to create test files
    # setup_test_files()

    example_ambiguous_file_resolution()
    example_specific_file_reading()