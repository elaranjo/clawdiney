## ADDED Requirements

### Requirement: agent_id column with backward-compatible default
`documents`, `entities`, and any write-path tables SHALL carry an `agent_id TEXT NOT NULL DEFAULT 'default'` column. Existing rows and installs with no `agent_id` concept SHALL continue to function unchanged under the `"default"` namespace.

#### Scenario: Pre-existing install unaffected
- **WHEN** an existing `brain.db` is migrated to add `agent_id`
- **THEN** all existing rows receive `agent_id = 'default'` and all existing queries (which don't pass `agent_id`) behave exactly as before

#### Scenario: New agent writes isolated
- **WHEN** two different `agent_id` values write facts about entities with the same name
- **THEN** each agent's entities are stored as distinct rows scoped to its own `agent_id`

### Requirement: Optional agent_id scoping on MCP tools
`search_brain`, `explore_graph`, `resolve_note`, `get_note_chunks`, `get_project_card`, `how_do_projects_relate`, and `write_memory` SHALL accept an optional `agent_id` parameter defaulting to `"default"`; when provided, results/writes are scoped to that namespace only.

#### Scenario: Scoped search
- **WHEN** `search_brain(query, agent_id="agent-b")` is called
- **THEN** only chunks/entities belonging to `agent_id="agent-b"` (plus shared/global data, if configured) are returned

#### Scenario: Cross-agent isolation
- **WHEN** `agent-a` writes a fact via `write_memory`
- **THEN** `search_brain` called with `agent_id="agent-b"` does not return that fact

### Requirement: Cross-agent graph queries remain possible
`how_do_projects_relate` SHALL support an explicit opt-in to query across `agent_id` namespaces (e.g. `agent_id="*"` or an explicit list) for cases where cross-agent graph relationships are intentionally desired.

#### Scenario: Explicit cross-agent query
- **WHEN** `how_do_projects_relate(a, b, agent_id="*")` is called
- **THEN** relations across all namespaces are considered, not just `"default"`
