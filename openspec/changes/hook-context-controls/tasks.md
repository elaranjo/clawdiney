## 1. Banner fix

- [x] 1.1 Change README banner `<img src>` to `https://raw.githubusercontent.com/elaranjo/clawdiney/main/assets/clawdiney-image.jpeg`
- [x] 1.2 Verify the URL loads (fetch it directly) before committing

## 2. Proactive hook: session + per-prompt result count

- [x] 2.1 Read `CLAWDINEY_HOOK_N_RESULTS` env var in `claude_hook_context.py`, parse as int, fall back to `N_RESULTS = 3` default when unset or invalid
- [x] 2.2 Parse and strip an inline `@nN` marker (case-insensitive, first match only) from the prompt text before building the query string
- [x] 2.3 Apply precedence: inline marker > env var > default
- [x] 2.4 Treat a resolved count of 0 as "skip retrieval, inject nothing" (no query call, no output)
- [x] 2.5 Update the module docstring with the new env var and marker syntax
- [x] 2.6 Manual test: run the hook script directly with sample stdin JSON for (a) no override, (b) env var set, (c) inline marker, (d) marker overriding env var, (e) count=0

## 3. search_brain n_results parameter

- [x] 3.1 Add `n_results` parameter to `search_brain` in `mcp_server.py`, defaulting to `SEARCH_N_RESULTS_DEFAULT`
- [x] 3.2 Thread `n_results` through to `engine.retrieve(...)` and `engine.build_context(...)`
- [x] 3.3 Handle `n_results=0`: skip retrieval, return an explicit "0 results requested" message distinct from the "no results found" wording
- [x] 3.4 Add/update tests in `tests/test_mcp_server.py`: default unchanged, explicit count respected, zero handled explicitly

## 4. Docs

- [x] 4.1 Document `CLAWDINEY_HOOK_N_RESULTS` and the `@nN` marker in README's hook-setup section (near the existing proactive-hook install instructions, if present) and in `scripts/claude_hook_context.py`'s docstring
- [x] 4.2 Document `search_brain`'s new `n_results` parameter in README's Read Tools list and CLAUDE.md's Integration section

## 5. Verification

- [x] 5.1 Run full test suite (`./venv/bin/python3 -m pytest tests/ -v`) and ruff (`./venv/bin/ruff check src/clawdiney/ tests/`)
- [x] 5.2 Manually exercise the hook end-to-end (real `BrainQueryEngine`, real vault) for at least one non-default case to confirm it works outside of mocks — covered by task 2.6's manual runs (env var, marker, precedence, zero) against the real vault/Ollama, no mocks
