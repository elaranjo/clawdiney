## ADDED Requirements

### Requirement: Optional n_results parameter on search_brain
The `search_brain` MCP tool SHALL accept an optional `n_results` parameter (default: the existing `SEARCH_N_RESULTS_DEFAULT`, currently 3) and pass it through to the underlying retrieval call.

#### Scenario: Default unchanged when omitted
- **WHEN** `search_brain(query)` is called without `n_results`
- **THEN** it behaves identically to current behavior (3 results)

#### Scenario: Explicit count requested
- **WHEN** `search_brain(query, n_results=10)` is called
- **THEN** up to 10 results are retrieved and included in the response briefing

### Requirement: Zero explicitly skips retrieval
`search_brain` called with `n_results=0` SHALL skip retrieval and return an explicit message stating no search was performed, rather than silently falling back to the default or returning an empty "no results found" message indistinguishable from a real empty search.

#### Scenario: Zero requested
- **WHEN** `search_brain(query, n_results=0)` is called
- **THEN** the tool returns without querying storage, and the response text distinguishes "0 results requested" from "search ran but found nothing"
