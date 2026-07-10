## Context

`scripts/claude_hook_context.py` is a `UserPromptSubmit` hook: Claude Code spawns it fresh per prompt, feeds `{"prompt": str, "cwd": str, ...}` on stdin, and injects whatever JSON it prints to stdout as `additionalContext`. It has no persistent state across invocations (each is a new process) other than what the environment or the prompt text itself carries in. `N_RESULTS = 3` is currently a module constant.

`search_brain` (MCP tool, `src/clawdiney/mcp_server.py`) calls `engine.retrieve(query, vault_override=vault, agent_id=agent_id)` — `retrieve()` already accepts `n_results` (default `SEARCH_N_RESULTS_DEFAULT = 3` from `constants.py`) but the tool never threads a caller-supplied value through.

The README banner `<img src="assets/clawdiney-image.jpeg">` is vault-relative; GitHub resolves relative paths against the repo tree when rendering `README.md`, but PyPI's README renderer has no such resolution — it needs an absolute URL.

## Goals / Non-Goals

**Goals:**
- Session-scoped control over the proactive hook's result count via an environment variable, so a user can widen/narrow/disable it for an entire terminal session without touching code.
- Per-prompt control via an inline marker in the prompt text, for one-off overrides.
- Expose `n_results` on the `search_brain` MCP tool so an agent can decide per-call.
- Support the full 0–N range, with 0 meaning "don't search" (hook: no context injected; tool: explicit zero-results response, not silently coerced to a default).
- Fix the banner so it renders on both GitHub and PyPI.

**Non-Goals:**
- Not adding a persistent "session" concept beyond the shell environment — Claude Code doesn't expose a stable session id to hook subprocesses, so "per session" here means "per shell/env, for as long as the export is active," not a Claude Code-native session store.
- Not touching `explore_graph`, `get_project_card`, or other read tools' result counts — out of scope, the proposal only covers `search_brain` and the proactive hook.
- Not changing the hook's other defaults (`ENABLE_RERANK=false`, `MIN_PROMPT_LENGTH`).

## Decisions

### 1. Inline marker syntax: `@nN` (e.g. `@n8`, `@n0`), matched anywhere in the prompt, case-insensitive, stripped before the rest of the hook logic runs
Chosen over a prefix-only or suffix-only requirement because prompts are free text and users won't reliably remember positional rules; a simple regex (`@n(\d+)\b`) scanned across the whole string is more forgiving. Only the first match is honored (multiple markers are almost certainly a typo, not intentional). The marker is stripped from the string used for the actual `engine.query(...)` call so it doesn't pollute the search query itself, but the *original* prompt (marker included) is what Claude Code processes normally — the hook only observes the prompt, it doesn't rewrite what the agent sees. Alternative considered: a leading `/n8` slash-command style — rejected because leading `/` is visually similar to Claude Code's actual slash commands and could confuse users into thinking it's a registered command.

### 2. Precedence: inline marker > `CLAWDINEY_HOOK_N_RESULTS` env var > hardcoded default (3)
Most specific wins. A one-off inline override shouldn't require unsetting a session env var first.

### 3. `n_results=0` is an explicit "skip", not clamped up to some minimum
For the hook: return with no output (identical to today's existing silent-no-op paths for empty prompts / Ollama down / no results) — zero sources means zero context, not "at least 1." For `search_brain`: still run the tool (so the caller gets a real response, not a hang) but skip retrieval and return a short explicit message ("0 results requested — no search performed") rather than quietly defaulting to 3, so an agent that requested 0 isn't confused by unexpected results appearing anyway.

### 4. `search_brain`'s `n_results` param has no artificial upper bound in code — relies on existing `fetch_k = n_results * 3` fan-out and normal query latency to self-limit
Adding a hard cap (e.g. 50) was considered but rejected as unnecessary defensive coding: the existing retrieval path already degrades gracefully (fail-soft per retriever, reranker is O(n) predict calls) and a user deliberately asking for 30 results has a legitimate reason; artificially capping it would silently violate what they asked for. Pathological input (e.g. `n_results=999999`) is bounded by Python/SQLite behavior (LIMIT clause), not a special-cased guard.

### 5. Banner fix: absolute `https://raw.githubusercontent.com/elaranjo/clawdiney/main/assets/clawdiney-image.jpeg`
Standard fix for this exact class of problem (relative image paths breaking on PyPI); pins to `main` branch (matches the repo's actual default branch) rather than a tag, so the image updates automatically if `assets/clawdiney-image.jpeg` is ever replaced, consistent with how the badge URLs earlier in the same README already reference `main`/`elaranjo/clawdiney`.

## Risks / Trade-offs

- [Env var set once and forgotten, causing confusing "why does search only return 1 result" later] → Document `CLAWDINEY_HOOK_N_RESULTS` in the hook's own module docstring (already the pattern used for its other env-var defaults) and in README's hook-setup instructions, and have the hook's `systemMessage` output include the effective count so it's visible every time (already partially done — `systemMessage` already reports `n_sources` found; extend it to also show when a non-default count was requested).
- [Inline marker regex accidentally matches something in normal prose, e.g. a prompt literally containing "@n8" as an unrelated token] → Low probability (the pattern is specific: `@n` immediately followed by digits), and the worst case is a slightly different result count for one prompt, not a crash or data issue — acceptable risk for a convenience feature.
- [`n_results=0` on `search_brain` could be misread by an agent as "tool failed" rather than "explicitly returned nothing"] → The returned message explicitly states "no search performed," distinct from the existing "no results found" wording used when a real search comes back empty.

## Migration Plan

Purely additive — no schema, no breaking signature changes (new params are optional with defaults matching current behavior). Land in one pass:
1. Fix the README banner URL.
2. Add `CLAWDINEY_HOOK_N_RESULTS` + inline `@nN` marker parsing to the hook script.
3. Add `n_results` param to `search_brain`.
4. Update README/CLAUDE.md hook documentation with the new controls.

Rollback: revert the commit; nothing persisted to migrate back.

## Open Questions

None — scope is small and self-contained enough that no decisions need to be deferred.
