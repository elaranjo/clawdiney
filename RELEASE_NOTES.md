# Release Notes

## Version 1.2.0 (2026-04-20)

### Retrieval-First Contract
`BrainQueryEngine` is now the single active engine abstraction. MCP is centered on `search_brain`, with `resolve_note` and `get_note_chunks` for note discovery and drill-down.

### Canonical Note Paths
Notes now move toward canonical vault-relative `path` identifiers in vector metadata and graph nodes, reducing filename collisions.

### Indexer Refactor
`brain_indexer.py` now exposes explicit functions and `main()`. Importing the module no longer triggers indexing side effects.

### Reranker Fallback
If the reranker model is unavailable or produces no passing scores, the system now falls back to the original vector ranking instead of returning an empty result set.

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
