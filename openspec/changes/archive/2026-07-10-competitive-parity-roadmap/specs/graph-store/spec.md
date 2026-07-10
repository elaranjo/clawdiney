## MODIFIED Requirements

### Requirement: Typed graph in SQLite
The system SHALL store the knowledge graph as relational tables in the same SQLite database: `entities(id, name, kind, description, agent_id, valid_at, invalidated_at, is_conflict)` and `relations(source_id, target_id, rel_type, evidence_chunk_id, confidence, agent_id, valid_at, invalidated_at, is_conflict)`. Neo4j MUST NOT be required.

#### Scenario: Indexing builds graph rows
- **WHEN** the indexer processes a note containing WikiLinks and tags
- **THEN** the note appears as an entity of kind `note`, each WikiLink target as a `LINKS_TO` relation, and each tag as a `HAS_TAG` relation to a `tag` entity, all created with `agent_id="default"`, `valid_at` set, `invalidated_at` NULL, `is_conflict=0`

#### Scenario: Deduplicated relations
- **WHEN** the same WikiLink appears twice in one note or the note is re-indexed
- **THEN** exactly one currently-valid relation row exists per (source, target, rel_type, agent_id)

## ADDED Requirements

### Requirement: Bi-temporal and conflict columns
`entities` and `relations` SHALL carry `valid_at`, `invalidated_at` (nullable), and `is_conflict` (default 0) columns as defined by the `temporal-facts` and `conflict-resolution` capabilities, additive to the existing schema.

#### Scenario: Existing schema extended without breakage
- **WHEN** the migration adding these columns runs against an existing `brain.db`
- **THEN** all pre-existing graph queries continue to return the same rows they did before migration (scoped to `agent_id="default"`, current-only facts)

### Requirement: Agent-scoped graph rows
`entities` and `relations` SHALL carry an `agent_id` column as defined by the `agent-namespacing` capability, defaulting to `"default"`.

#### Scenario: Namespace isolation in graph traversal
- **WHEN** multi-hop traversal is requested with a specific `agent_id`
- **THEN** only entities and relations in that namespace are traversed, unless cross-namespace traversal is explicitly requested
