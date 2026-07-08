# embedding-abstraction

## Requirements

### Requirement: All embeddings flow through EmbeddingProvider
Every embedding generation in the codebase (query engine, indexer, incremental indexer, vault writer) SHALL go through the `EmbeddingProvider` protocol from `embedding_providers.py`. Direct calls to `ollama.embeddings()` or `ollama.embed()` outside provider implementations MUST NOT exist.

#### Scenario: Query embedding via provider
- **WHEN** the query engine embeds a search query
- **THEN** it calls `provider.embed(text)` on its configured provider instance

#### Scenario: Batch indexing via provider
- **WHEN** the indexer embeds multiple chunks
- **THEN** it calls `provider.embed_batch(texts)` so providers with native batch APIs use them

### Requirement: Ollama provider uses current API
`OllamaEmbeddingProvider` SHALL use the `ollama.embed()` API (not the deprecated `ollama.embeddings()`), handling its response shape (`embeddings` list) including native batch input.

#### Scenario: Single embed
- **WHEN** `embed("text")` is called
- **THEN** it invokes `client.embed(model=..., input="text")` and returns the first vector as `list[float]`

#### Scenario: Native batch embed
- **WHEN** `embed_batch(["a", "b"])` is called
- **THEN** it invokes `client.embed(model=..., input=["a", "b"])` once and returns two vectors

### Requirement: Provider selection by config
The active provider SHALL be selected via configuration (default `ollama`), using the existing `get_embedding_provider()` factory. Retry with exponential backoff (tenacity, 3 attempts) SHALL wrap provider calls at the call site or inside the provider, preserving current resilience behavior.

#### Scenario: Default provider
- **WHEN** no provider is configured
- **THEN** the Ollama provider with `Config.MODEL_NAME` is used

#### Scenario: Transient failure retried
- **WHEN** the provider raises a ConnectionError once and then succeeds
- **THEN** the embedding call succeeds without surfacing the error
