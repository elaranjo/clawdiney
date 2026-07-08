# graph-store (delta)

## MODIFIED Requirements

### Requirement: Multi-hop traversal
The graph store SHALL support neighborhood expansion up to a configurable depth (default 1, max 3) via recursive CTE, returning each related entity with its relation type and hop distance. Traversal SHALL cover all entity kinds (`note`, `tag`, `project`, `service`, `library`, `datastore`, `pattern`) and results SHALL include each entity's kind, relation confidence, and evidence reference (chunk path) when present. The store SHALL also support path finding between two named entities (up to 3 hops), returning each hop's source, relation type, target, confidence, and evidence.

#### Scenario: Two-hop expansion
- **WHEN** A links to B and B links to C, and traversal depth is 2
- **THEN** expanding from A returns B (distance 1) and C (distance 2)

#### Scenario: Cycle safety
- **WHEN** the graph contains a cycle (A→B→A)
- **THEN** traversal terminates and returns each entity at its minimum distance exactly once

#### Scenario: Mixed-kind expansion
- **WHEN** a project entity has relations to libraries and patterns
- **THEN** expansion returns those entities with their kind and relation type included

#### Scenario: Path between two entities
- **WHEN** projects A and B share a library X
- **THEN** path finding between A and B returns the two-hop path through X with relation types per hop

#### Scenario: No path within limit
- **WHEN** two entities are not connected within 3 hops
- **THEN** path finding returns an empty result (no exception)
