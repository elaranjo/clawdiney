# Changelog

## [1.2.0] - 2026-04-20

### Added
- `resolve_note(name)` and `get_note_chunks(path)` as the canonical MCP drill-down workflow
- explicit `main()` and pure indexing helpers in `brain_indexer.py`
- reranker fallback to preserve vector results when reranking fails

### Changed
- standardized on `BrainQueryEngine` as the active engine abstraction
- moved note identity toward canonical vault-relative `path`
- updated tests and examples to match the retrieval-first contract
- kept full-file reading outside the MCP surface

### Removed
- broken `read_full_note` MCP flow
- stale `BrainEngine` references from active code paths

## [1.1.0] - 2026-04-19

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
