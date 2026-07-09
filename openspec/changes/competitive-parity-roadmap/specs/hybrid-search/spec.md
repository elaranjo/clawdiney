## MODIFIED Requirements

### Requirement: Cross-encoder reranking
The system SHALL rerank fused candidates with a cross-encoder model, loaded from a configurable `RERANK_MODEL` setting (default `BAAI/bge-reranker-v2-m3`) via `sentence-transformers`, scoring (query, chunk) pairs directly. The system MUST NOT use generative LLM prompting with textual score parsing for reranking.

#### Scenario: Rerank applied
- **WHEN** a query runs with reranking enabled and more candidates than `n_results` are fused
- **THEN** the final top-N ordering follows cross-encoder scores, descending

#### Scenario: Reranker unavailable
- **WHEN** the cross-encoder model cannot be loaded (missing dependency or model files)
- **THEN** the system logs a warning and returns the RRF-fused ranking unchanged

#### Scenario: Rerank disabled by config
- **WHEN** `ENABLE_RERANK` is false
- **THEN** no cross-encoder model is loaded and RRF ordering is returned

#### Scenario: Alternate model configured
- **WHEN** `RERANK_MODEL` is set to a non-default cross-encoder model name
- **THEN** the reranker loads and scores using that model instead of the default

## ADDED Requirements

### Requirement: Namespace and temporal scoping on hybrid queries
Hybrid search SHALL accept optional `agent_id` and `as_of` parameters; when provided, retrieval and graph-join steps are scoped to that agent namespace and to facts valid at that timestamp, respectively, defaulting to `agent_id="default"` and current-time validity when omitted.

#### Scenario: Default query unaffected
- **WHEN** a hybrid search query is made with no `agent_id` or `as_of` parameters
- **THEN** results are identical to current behavior (default namespace, current facts only)

#### Scenario: Scoped and temporal query combined
- **WHEN** a query is made with `agent_id="agent-b"` and `as_of` set to a past timestamp
- **THEN** only chunks/facts belonging to `agent-b` and valid at that timestamp are considered
