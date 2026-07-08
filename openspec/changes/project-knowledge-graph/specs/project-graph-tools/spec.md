# project-graph-tools

## ADDED Requirements

### Requirement: get_project_card MCP tool
The MCP server SHALL expose `get_project_card(name, vault=None)` returning the full Markdown content of a project's card. Ambiguous or unknown names MUST return candidate suggestions instead of an error.

#### Scenario: Exact project name
- **WHEN** an agent calls `get_project_card("clawdiney")`
- **THEN** the full card content is returned with its vault-relative path

#### Scenario: Unknown project
- **WHEN** the name matches no card
- **THEN** the tool returns a "not found" message listing closest candidates (by name fragment)

### Requirement: how_do_projects_relate MCP tool
The MCP server SHALL expose `how_do_projects_relate(project_a, project_b, vault=None)` returning graph paths (up to 3 hops) between the two project entities: each hop with source, relation type, target, confidence, and evidence reference when present.

#### Scenario: Direct shared dependency
- **WHEN** projects A and B both depend on library X
- **THEN** the tool returns the path A -DEPENDS_ON-> X <-DEPENDS_ON- B

#### Scenario: No connection
- **WHEN** no path exists within 3 hops
- **THEN** the tool states no relationship was found (not an error)

#### Scenario: Unknown project name
- **WHEN** either name matches no project entity
- **THEN** the tool returns a "not found" message naming which argument failed

### Requirement: explore_graph shows typed relations
`explore_graph` SHALL include, for non-note entities, the entity kind and relation type in its output, and evidence source when available.

#### Scenario: Exploring a project entity
- **WHEN** an agent calls `explore_graph("clawdiney")`
- **THEN** connected entities are listed with kind and relation type (e.g., `sqlite-vec [library] via DEPENDS_ON`)
