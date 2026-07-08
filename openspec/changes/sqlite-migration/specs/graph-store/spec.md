# graph-store

## ADDED Requirements

### Requirement: Typed graph in SQLite
The system SHALL store the knowledge graph as relational tables in the same SQLite database: `entities(id, name, kind, description)` and `relations(source_id, target_id, rel_type, evidence_chunk_id, confidence)`. Neo4j MUST NOT be required.

#### Scenario: Indexing builds graph rows
- **WHEN** the indexer processes a note containing WikiLinks and tags
- **THEN** the note appears as an entity of kind `note`, each WikiLink target as a `LINKS_TO` relation, and each tag as a `HAS_TAG` relation to a `tag` entity

#### Scenario: Deduplicated relations
- **WHEN** the same WikiLink appears twice in one note or the note is re-indexed
- **THEN** exactly one relation row exists per (source, target, rel_type)

### Requirement: Related-notes neighborhood query
`get_related_notes` SHALL return notes connected to a given note (by path or name, scoped to a vault) through direct `LINKS_TO` relations in either direction and through shared tags, deduplicated — preserving the semantics of the current Neo4j query.

#### Scenario: WikiLink neighbors
- **WHEN** note A links to note B and note C links to note A
- **THEN** `get_related_notes("A")` includes both B and C

#### Scenario: Tag-based neighbors
- **WHEN** notes A and B share tag `#auth` and are not directly linked
- **THEN** `get_related_notes("A")` includes B

#### Scenario: Unknown note
- **WHEN** the note reference matches no entity
- **THEN** an empty list is returned (no exception)

### Requirement: Multi-hop traversal
The graph store SHALL support neighborhood expansion up to a configurable depth (default 1, max 3) via recursive CTE, returning each related entity with its relation type and hop distance.

#### Scenario: Two-hop expansion
- **WHEN** A links to B and B links to C, and traversal depth is 2
- **THEN** expanding from A returns B (distance 1) and C (distance 2)

#### Scenario: Cycle safety
- **WHEN** the graph contains a cycle (A→B→A)
- **THEN** traversal terminates and returns each entity at its minimum distance exactly once

### Requirement: Evidence traceability
Each relation SHALL be traceable to its origin: relations derived from vault parsing carry `confidence = 1.0`; relations extracted by an LLM (future capability) carry the model's confidence and an `evidence_chunk_id` pointing at the chunk that supports them.

#### Scenario: Parsed relation provenance
- **WHEN** a `LINKS_TO` relation is created from a WikiLink during indexing
- **THEN** its confidence is 1.0

### Requirement: Vault-scoped graph
All graph queries SHALL be scoped by vault, matching the current `{vault: $vault}` Neo4j filter.

#### Scenario: Cross-vault isolation
- **WHEN** two vaults contain notes with the same name
- **THEN** `get_related_notes(name, vault="a")` returns only vault `a` neighbors
