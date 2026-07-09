## ADDED Requirements

### Requirement: Golden query fixture set
The system SHALL maintain a versioned golden-query fixture (`tests/eval/golden_queries.jsonl`) of `(query, expected_note_paths, expected_chunk_ids)` records, evaluated against a dedicated fixture vault snapshot independent of the user's live vault.

#### Scenario: Fixture is reproducible
- **WHEN** the eval harness runs twice against an unchanged fixture vault and golden set
- **THEN** it produces identical metric values both times

#### Scenario: Fixture vault isolated from live vault
- **WHEN** the user's live vault changes
- **THEN** eval harness scores are unaffected because it indexes the fixture vault, not the live one

### Requirement: Retrieval quality metrics
The eval harness SHALL compute recall@k, Mean Reciprocal Rank (MRR), and hit rate for each golden query, comparing retrieved note/chunk IDs against expected ones, and report per-query and aggregate scores.

#### Scenario: Perfect retrieval
- **WHEN** every golden query's top-k results contain all expected chunk IDs
- **THEN** recall@k = 1.0 and hit rate = 1.0 for the run

#### Scenario: Partial retrieval
- **WHEN** a golden query's expected chunk appears at rank 3 of 5
- **THEN** MRR for that query is 1/3 and it is included in the aggregate

### Requirement: CLI runner with regression gate
The system SHALL provide a CLI entry point (e.g. `clawdiney-eval`) that runs the harness, prints aggregate scores, and exits non-zero if any metric drops below a configured threshold relative to a stored baseline.

#### Scenario: Regression detected
- **WHEN** aggregate recall@k drops more than the configured tolerance below the stored baseline
- **THEN** the CLI exits with a non-zero status and prints which queries regressed

#### Scenario: No regression
- **WHEN** all metrics are at or above baseline within tolerance
- **THEN** the CLI exits 0 and prints the aggregate scores

### Requirement: Component isolation in evaluation
The eval harness SHALL support running with reranking enabled/disabled and with BM25-only, vector-only, or hybrid retrieval, so each component's contribution to retrieval quality is measurable independently.

#### Scenario: Compare hybrid vs BM25-only
- **WHEN** the harness runs once in hybrid mode and once in BM25-only mode against the same golden set
- **THEN** it reports both aggregate score sets so the marginal contribution of vector search is visible
