## Why

Two independent papercuts: (1) the README banner uses a vault-relative `<img src>` that GitHub resolves but PyPI's README renderer cannot, so the banner is broken on the PyPI project page; (2) the proactive context hook (`scripts/claude_hook_context.py`) and the `search_brain` MCP tool both hardcode `n_results=3` with no way to change it, so a user who wants a broader (or narrower, or disabled) proactive search has no lever — everything defaults to exactly 3 sources regardless of session or prompt.

## What Changes

- Fix the README banner `<img>` to an absolute `raw.githubusercontent.com` URL so it renders identically on GitHub and PyPI.
- Add a **session-level** override: the proactive hook reads `CLAWDINEY_HOOK_N_RESULTS` (falls back to the current default of 3 when unset), so exporting it once in a shell changes proactive search breadth for every prompt in that terminal session.
- Add a **per-prompt** override: the proactive hook recognizes a leading/trailing inline marker in the prompt text (e.g. `@n8`, `@n0`) and uses that count for just that one query, stripping the marker before the prompt is otherwise processed.
- Add an `n_results` parameter to the `search_brain` MCP tool (already supported internally by `BrainQueryEngine.retrieve`/`query`, just never exposed at the tool boundary) so an agent can explicitly ask for more or fewer results per call.
- All three controls accept the range **0 to N**: 0 disables that search entirely (proactive hook: silently returns no context; `search_brain`: returns an explicit "0 results requested" message rather than performing a no-op query).

## Capabilities

### New Capabilities
- `proactive-context-hook-controls`: session-level (env var) and per-prompt (inline marker) control over how many sources `scripts/claude_hook_context.py` injects per prompt, including disabling it (0).
- `search-brain-result-count`: optional `n_results` parameter on the `search_brain` MCP tool, including 0 to explicitly request no results.

### Modified Capabilities
(none — `hybrid-search`'s underlying retrieval already supports a variable `n_results`; this change only exposes existing capability at two new call sites)

## Impact

- `README.md` - banner `<img src>` becomes an absolute URL.
- `scripts/claude_hook_context.py` - reads `CLAWDINEY_HOOK_N_RESULTS` env var; parses and strips an inline `@nN` marker from the prompt; handles `n_results=0` as an explicit skip.
- `src/clawdiney/mcp_server.py` - `search_brain` gains an `n_results` parameter, threaded to `engine.retrieve`/`build_context`.
- No schema/storage changes; no new dependencies.
