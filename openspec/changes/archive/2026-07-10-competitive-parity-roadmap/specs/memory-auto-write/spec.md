## ADDED Requirements

### Requirement: write_memory MCP tool
The MCP server SHALL expose a `write_memory(fact, source, agent_id?)` tool that accepts a natural-language fact and a source label, and persists it as a vault note update — the system MUST NOT passively infer facts from `search_brain` or other read-path tool calls.

#### Scenario: Explicit fact write
- **WHEN** an agent calls `write_memory("User prefers embedded SQLite over Docker-based stacks", source="conversation")`
- **THEN** the fact is normalized, resolved against existing entities, and written to the vault; the tool returns the resulting note path

#### Scenario: Read calls have no write side effect
- **WHEN** an agent calls `search_brain` or `explore_graph`
- **THEN** no vault note is created or modified as a result

### Requirement: Fact normalization and dedupe before write
Before writing, the system SHALL resolve the fact's subject entity via the existing entity-resolution similarity threshold (`ENTITY_RESOLUTION_THRESHOLD`) and SHALL NOT create a duplicate entity or duplicate note section for a fact that already exists in equivalent form.

#### Scenario: Duplicate fact
- **WHEN** `write_memory` is called twice with semantically equivalent facts about the same entity
- **THEN** the second call updates the existing note section (or is a no-op) instead of creating a duplicate

#### Scenario: New entity below resolution threshold
- **WHEN** the fact's subject does not match any existing entity above the resolution threshold
- **THEN** a new entity and a new note are created

### Requirement: Provenance-marked memory area
Auto-written facts SHALL be written to a distinguishable vault location (or carry a `source: agent` frontmatter marker) so they are visually distinguishable from manually curated notes.

#### Scenario: Provenance visible
- **WHEN** a user opens a note created via `write_memory` in Obsidian
- **THEN** the note's frontmatter or location clearly indicates it was agent-written, not manually authored

### Requirement: Minimum confidence gate
The system SHALL reject or flag-for-review `write_memory` calls whose extracted fact confidence falls below a configured minimum, to avoid polluting the vault with low-quality writes.

#### Scenario: Low-confidence fact rejected
- **WHEN** a fact's confidence score (from normalization/extraction) is below the configured minimum
- **THEN** the write is rejected and the tool response indicates the reason
