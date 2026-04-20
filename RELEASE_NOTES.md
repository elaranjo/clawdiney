# Release Notes

## Version 1.2.0 (2026-04-20)

### Unified ChromaDB Configuration
The system now exclusively uses the HTTP client for ChromaDB, simplifying configuration and eliminating the complexity of choosing between persistent and HTTP clients.

### Automatic Resource Management
BrainEngine now supports context manager protocol:
```python
# Automatic usage with connection closing
with BrainEngine() as engine:
    result = engine.search("my query")
# Connections are automatically closed
```

### Intelligent File Resolution
When multiple files have the same name, the system lists all candidates:
```
Multiple files found for 'design.md' (3 matches):
- frontend/design.md
- backend/design.md
- mobile/design.md

Please specify which file you want to read.
```

## Version 1.1.0 (2026-04-19)

### Added
- Centralized configuration management with `config.py`
- Support for both HTTP and Persistent ChromaDB clients via `CHROMA_CLIENT_TYPE` environment variable
- Proper connection closing for BrainEngine to prevent connection leaks
- Enhanced error handling in BrainEngine initialization
- Improved file resolution in `read_note` method to handle duplicate filenames
- Unit tests for configuration and engine classes
- Test runner script (`run_tests.sh`)

### Changed
- Fixed hardcoded path in `CHROMA_PATH` configuration
- Standardized ChromaDB client usage across all modules
- Improved error messages and handling throughout the codebase
- Updated `.env` file with new configuration options
- Updated documentation in `CLAUDE.md`

### Fixed
- Inconsistent ChromaDB client usage between modules
- Missing `close()` method in BrainEngine
- Fragile file lookup in `read_note` method
- Lack of error handling in BrainEngine initialization
- Missing unit tests

### Security
- Removed personal path information from default configuration