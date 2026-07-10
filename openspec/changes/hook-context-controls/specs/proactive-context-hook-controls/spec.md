## ADDED Requirements

### Requirement: Session-level result count via environment variable
`scripts/claude_hook_context.py` SHALL read its proactive-search result count from the `CLAWDINEY_HOOK_N_RESULTS` environment variable when set, falling back to the existing default of 3 when unset or invalid (non-integer).

#### Scenario: Env var overrides default for the session
- **WHEN** `CLAWDINEY_HOOK_N_RESULTS=8` is exported before the Claude Code session starts
- **THEN** every proactive hook invocation in that session queries with `n_results=8`

#### Scenario: Unset env var preserves current behavior
- **WHEN** `CLAWDINEY_HOOK_N_RESULTS` is not set
- **THEN** the hook uses `n_results=3`, identical to current behavior

#### Scenario: Invalid value falls back to default
- **WHEN** `CLAWDINEY_HOOK_N_RESULTS` is set to a non-integer value
- **THEN** the hook falls back to the default (3) rather than raising or crashing the hook

### Requirement: Per-prompt result count via inline marker
The hook SHALL recognize an inline `@nN` marker (N = a non-negative integer, case-insensitive `@N`/`@n` accepted) anywhere in the submitted prompt text, use N as that single query's result count, and strip the marker from the text passed to the retrieval query.

#### Scenario: Inline marker overrides session/default for one prompt
- **WHEN** the user's prompt contains `@n8` (e.g. "explain the auth flow @n8")
- **THEN** that prompt's proactive query runs with `n_results=8` and the marker text is not sent to the query engine as part of the search text

#### Scenario: Marker only affects the current prompt
- **WHEN** a prompt with `@n8` is followed by a later prompt with no marker
- **THEN** the later prompt uses the session env var (if set) or the default (3), not 8

#### Scenario: Malformed marker ignored
- **WHEN** the prompt contains `@n` with no following digits (e.g. "@nice")
- **THEN** it is not treated as a marker and the prompt text is used unmodified

### Requirement: Precedence between inline marker, session env var, and default
When multiple sources specify a result count, the hook SHALL apply inline marker > `CLAWDINEY_HOOK_N_RESULTS` > default (3), in that order.

#### Scenario: Inline marker wins over env var
- **WHEN** `CLAWDINEY_HOOK_N_RESULTS=8` is set and the prompt contains `@n2`
- **THEN** that prompt's query runs with `n_results=2`

### Requirement: Zero results disables the proactive search
A resolved result count of 0 (from either the env var or the inline marker) SHALL cause the hook to skip retrieval entirely and inject no additional context, without treating 0 as an error or falling back to the default.

#### Scenario: Env var set to 0
- **WHEN** `CLAWDINEY_HOOK_N_RESULTS=0` is set
- **THEN** the hook performs no query and injects no context for any prompt in that session

#### Scenario: Inline marker set to 0
- **WHEN** a single prompt contains `@n0`
- **THEN** only that prompt's proactive search is skipped; subsequent prompts revert to the session/default count
