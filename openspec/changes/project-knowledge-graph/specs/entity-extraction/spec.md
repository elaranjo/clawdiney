# entity-extraction

## ADDED Requirements

### Requirement: Deterministic manifest extraction (layer 1)
The system SHALL parse project manifests (`pyproject.toml`, `package.json`, `docker-compose.yml`, `.env.example`) into typed entities and relations: the project itself (kind `project`), dependencies (kind `library`, relation `DEPENDS_ON`), declared services (kind `service`), and datastores (kind `datastore`, relations `SHARES_DB` when two projects reference the same datastore, `CALLS_API_OF` when config references another project's service). All layer-1 relations MUST carry `confidence = 1.0`.

#### Scenario: Python dependencies extracted
- **WHEN** layer 1 parses a `pyproject.toml` with dependencies
- **THEN** each dependency exists as a `library` entity with a `DEPENDS_ON` relation from the project entity

#### Scenario: Shared datastore detected
- **WHEN** two projects' configs reference the same database
- **THEN** both projects have relations to one shared `datastore` entity (not two duplicates)

#### Scenario: Malformed manifest
- **WHEN** a manifest fails to parse
- **THEN** the file is skipped with a logged warning and extraction continues with the remaining files

### Requirement: LLM semantic extraction (layer 2)
The system SHALL extract semantic entities/relations (`pattern` entities; `USES_PATTERN`, `IMPLEMENTS`, `MENTIONS` relations) from project cards via a structured-output LLM prompt (closed enum of kinds/relation types, JSON response). Each extracted relation MUST store the model's confidence (< 1.0) and an `evidence_chunk_id` pointing at the supporting card chunk. Layer 2 SHALL run only when the project card's content hash changed since the last extraction.

#### Scenario: Pattern usage extracted with evidence
- **WHEN** a card states the project uses the repository pattern
- **THEN** a `USES_PATTERN` relation links the project to a `pattern` entity, with confidence < 1.0 and evidence pointing at the card chunk containing the statement

#### Scenario: Invalid LLM output
- **WHEN** the LLM returns malformed JSON or values outside the enum
- **THEN** the invalid items are discarded with a logged warning and no partial garbage is written

#### Scenario: Unchanged card skipped
- **WHEN** extraction runs and the card hash matches the last extraction
- **THEN** no LLM call is made

### Requirement: Entity resolution before insert
Before inserting an LLM-extracted entity, the system SHALL search existing entities of the same kind by embedding similarity of name+description; above a configurable threshold the existing entity is reused instead of creating a duplicate.

#### Scenario: Near-duplicate merged
- **WHEN** extraction produces "jwt auth" and a `pattern` entity "JWT Authentication" already exists with similarity above threshold
- **THEN** relations attach to the existing entity and no new entity row is created

#### Scenario: Distinct entity created
- **WHEN** no existing entity clears the similarity threshold
- **THEN** a new entity row is created

### Requirement: Re-extraction replaces prior layer output
Re-running extraction for a project SHALL replace that project's previously extracted relations of the same layer (no accumulation of stale relations), while leaving relations from other layers and other projects untouched.

#### Scenario: Dependency removed from manifest
- **WHEN** a dependency is removed and layer 1 re-runs
- **THEN** its `DEPENDS_ON` relation is gone and other projects' relations are unchanged
