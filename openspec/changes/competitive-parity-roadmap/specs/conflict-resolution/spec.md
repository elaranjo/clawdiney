## ADDED Requirements

### Requirement: Contradiction detection at write time
When a new fact about a resolved entity would invalidate an existing current fact (per `temporal-facts`), the system SHALL compare the new and existing values; if they diverge beyond a normalization-aware similarity threshold, both SHALL be retained with `is_conflict = 1` rather than the old one being silently invalidated.

#### Scenario: Conflicting values detected
- **WHEN** an existing fact states entity X has property P = "A" and a new write states P = "B" for the same entity, and "A"/"B" are not equivalent after normalization
- **THEN** both rows are kept, each marked `is_conflict = 1`, and a `CONTRADICTS` relation is created between them

#### Scenario: Non-conflicting update
- **WHEN** a new fact is a refinement or equivalent restatement of the existing fact (within the similarity threshold)
- **THEN** the existing fact is invalidated normally per `temporal-facts` with no conflict marker

### Requirement: Conflict surfacing in query responses
`search_brain` and `explore_graph` MCP tool responses SHALL include a `conflicts` field listing any currently-unresolved contradictions touching the returned entities, without changing the existing response shape for callers that ignore the field.

#### Scenario: Query touches conflicted entity
- **WHEN** a search result includes a chunk/entity with an unresolved `CONTRADICTS` relation
- **THEN** the response's `conflicts` field describes both conflicting values and their sources

#### Scenario: No conflicts present
- **WHEN** no returned entity has an unresolved conflict
- **THEN** the `conflicts` field is an empty list and the rest of the response is unchanged from current behavior

### Requirement: Conflict resolution marking
The system SHALL support marking a conflict as resolved (choosing one fact as authoritative, invalidating the other), via an explicit vault-writer operation, after which the `conflicts` field no longer surfaces it.

#### Scenario: Conflict resolved
- **WHEN** a conflict is explicitly resolved in favor of one of the two facts
- **THEN** the losing fact's `invalidated_at` is set, `is_conflict` is cleared on both, and subsequent queries no longer report it in `conflicts`
