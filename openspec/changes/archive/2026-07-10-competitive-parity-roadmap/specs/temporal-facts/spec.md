## ADDED Requirements

### Requirement: Bi-temporal validity columns
`entities` and `relations` SHALL carry nullable `valid_at` (timestamp the fact became true) and `invalidated_at` (timestamp it stopped being true) columns. A row with `invalidated_at IS NULL` SHALL be considered currently valid.

#### Scenario: New fact is current
- **WHEN** a new entity or relation is written
- **THEN** it is created with `valid_at` set to the write time and `invalidated_at` NULL

#### Scenario: Fact superseded
- **WHEN** a fact about a resolved entity is updated with a new value
- **THEN** the old row's `invalidated_at` is set to the update time and a new row is inserted with `valid_at` at that same time, rather than the old row being overwritten in place

### Requirement: As-of query support
`get_related_notes`, graph traversal, and hybrid search graph joins SHALL support an optional `as_of` timestamp parameter; when provided, only facts valid at that timestamp (`valid_at <= as_of AND (invalidated_at IS NULL OR invalidated_at > as_of)`) are considered.

#### Scenario: Default query sees only current facts
- **WHEN** a query is made without an `as_of` parameter
- **THEN** only rows with `invalidated_at IS NULL` are returned, preserving current behavior

#### Scenario: Historical query
- **WHEN** a query is made with `as_of` set to a past timestamp
- **THEN** facts valid at that timestamp are returned, including ones since invalidated, and facts created after that timestamp are excluded

### Requirement: Schema migration for existing databases
The system SHALL detect a pre-migration `brain.db` (via schema version) and apply an additive migration adding the bi-temporal columns with `valid_at` backfilled from existing row creation time and `invalidated_at` NULL, without data loss.

#### Scenario: Migration on first open
- **WHEN** an existing `brain.db` created before this change is opened after upgrade
- **THEN** the migration runs automatically, all existing rows become currently-valid facts, and no existing query behavior changes

#### Scenario: Migration is idempotent
- **WHEN** the migration runs against an already-migrated database
- **THEN** it is a no-op and does not error
