# project-cards

## ADDED Requirements

### Requirement: Enriched project card structure
Generated project cards SHALL contain the sections: Purpose, Stack, Architecture, Interfaces, Conventions, and Entry Points. Stack, Interfaces, Conventions, and Entry Points MUST be derived deterministically from project files; Purpose and Architecture MAY be LLM-generated.

#### Scenario: Card generated for a Python project
- **WHEN** the project indexer analyzes a project containing `pyproject.toml` and a README
- **THEN** the card includes Stack (dependencies), Entry Points (scripts), Interfaces (exposed/consumed services), and a Purpose section of 2-3 sentences

#### Scenario: LLM unavailable
- **WHEN** Ollama is unreachable during card generation
- **THEN** the card is still generated with deterministic sections populated and Purpose/Architecture marked as pending, and no exception propagates

### Requirement: Interfaces section from deterministic parsing
The Interfaces section SHALL list what the project exposes (server ports, MCP servers, CLI commands) and consumes (databases, external services, URLs/ports found in configuration), each with the source file it was parsed from.

#### Scenario: Service consumption detected
- **WHEN** a project's config references a database URL or service port
- **THEN** the Interfaces section lists it under "Consumes" with the originating file

### Requirement: Cards indexed like vault notes
Project cards SHALL be written into the configured vault and flow through the standard indexing pipeline (chunks, vectors, FTS, graph), making them searchable via `search_brain`.

#### Scenario: Card searchable after generation
- **WHEN** a card is generated and the vault is synced
- **THEN** `search_brain` queries matching the project's purpose return chunks of the card

### Requirement: Card regeneration is idempotent and change-aware
Re-running the indexer over an unchanged project SHALL produce an identical card (no spurious diffs); LLM sections are regenerated only when deterministic inputs (manifest/README/structure digest) change.

#### Scenario: Unchanged project
- **WHEN** the indexer runs twice over an unchanged project
- **THEN** the card file content is identical and no LLM call is made on the second run
