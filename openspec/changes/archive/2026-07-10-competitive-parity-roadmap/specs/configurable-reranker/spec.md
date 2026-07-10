## ADDED Requirements

### Requirement: Configurable reranker model
The reranker SHALL load its cross-encoder model name from a `RERANK_MODEL` configuration value (default: `BAAI/bge-reranker-v2-m3`, preserving current behavior) instead of a hardcoded constant, so any `sentence-transformers`-compatible cross-encoder can be substituted without code changes.

#### Scenario: Default unchanged
- **WHEN** `RERANK_MODEL` is not set
- **THEN** the system loads `BAAI/bge-reranker-v2-m3`, identical to current behavior

#### Scenario: Alternate model configured
- **WHEN** `RERANK_MODEL` is set to a different valid cross-encoder model name
- **THEN** the reranker loads that model instead

### Requirement: Documented latency/precision trade-off
The system SHALL document (in config reference) the latency and precision trade-off between the default reranker, at least one smaller/faster alternative, and the no-rerank fast path (`ENABLE_RERANK=false`, already existing).

#### Scenario: Config docs list trade-offs
- **WHEN** a user reads the reranker configuration documentation
- **THEN** it states relative latency and eval-harness-measured precision for the default model, a faster alternative, and rerank-disabled mode

### Requirement: Model swap validated against eval harness
Changing `RERANK_MODEL` to a new default SHALL require a corresponding eval-harness run demonstrating no regression versus the prior default, recorded in the harness baseline.

#### Scenario: Regression blocks default change
- **WHEN** a candidate reranker model scores worse than the current baseline on the eval harness beyond tolerance
- **THEN** it MUST NOT be adopted as the new default `RERANK_MODEL`
