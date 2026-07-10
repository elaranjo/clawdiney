#!/usr/bin/env python3
"""
Claude Code UserPromptSubmit hook: proactively retrieves brain context
before every prompt, so the MCP knowledge base is consulted even if the
agent doesn't think to call search_brain itself.

Install: add to ~/.claude/settings.json under hooks.UserPromptSubmit
(alongside any other hooks already registered there):

    {
      "hooks": [
        {
          "type": "command",
          "command": "<venv>/bin/python3 <repo>/scripts/claude_hook_context.py",
          "timeout": 10,
          "statusMessage": "Querying clawdiney brain..."
        }
      ]
    }

Contract: Claude Code sends {"prompt": str, "cwd": str, ...} as JSON on
stdin. Whatever this script prints to stdout (exit code 0) is injected as
additional context before the prompt is processed. Any failure (Ollama
down, empty vault, timeout) must degrade to silent no-op — a broken brain
must never break a session.

Result count controls (0 disables the proactive search):
- Default: adaptive — the engine fetches up to 10 candidates and keeps only
  those whose RRF score holds up against the best hit, so narrow prompts
  inject 1-2 sources and broad prompts many more, with no manual tuning.
- Session-level: export CLAWDINEY_HOOK_N_RESULTS=<int|auto> before starting
  Claude Code. An integer pins a fixed count for every prompt; "auto" (or
  unset/invalid) keeps adaptive mode.
- Per-prompt: include an inline `@nN` marker anywhere in the prompt text
  (e.g. "explain the auth flow @n8"), or `@nauto` to force adaptive. The
  marker is stripped before the text is used as the search query and only
  affects that one prompt.
- Precedence: inline marker > CLAWDINEY_HOOK_N_RESULTS > adaptive default.
"""

import json
import logging
import os
import re
import sys
from pathlib import Path

MIN_PROMPT_LENGTH = 12
AUTO_N_RESULTS = -1  # SEARCH_N_RESULTS_AUTO: engine picks count by score cutoff
_MARKER_RE = re.compile(r"@n(\d+|auto)\b", re.IGNORECASE)

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

# Defaults mirroring the MCP server registration; only applied if unset,
# so an explicit environment (e.g. a future per-project override) wins.
os.environ.setdefault("VAULTS_DIR", "/home/ermanelaranjo/clawdiney-vaults")
os.environ.setdefault("MCP_DEFAULT_VAULT", "general")
os.environ.setdefault("MODEL_NAME", "bge-m3:latest")
os.environ.setdefault("BRAIN_DB_PATH", "/home/ermanelaranjo/.clawdiney/brain.db")
# Keep the hook fast: reranking adds real latency to every single prompt.
os.environ.setdefault("ENABLE_RERANK", "false")


def _detect_vault(cwd: Path, vaults: dict) -> str | None:
    parts = cwd.parts
    for part in reversed(parts):
        if part in vaults:
            return part
    return None


def _env_n_results() -> int:
    raw = os.environ.get("CLAWDINEY_HOOK_N_RESULTS")
    if raw is None or raw.strip().lower() == "auto":
        return AUTO_N_RESULTS
    try:
        value = int(raw)
    except ValueError:
        return AUTO_N_RESULTS
    return value if value >= 0 else AUTO_N_RESULTS


def _resolve_n_results(prompt: str) -> tuple[int, str]:
    """Inline `@nN`/`@nauto` marker > CLAWDINEY_HOOK_N_RESULTS > adaptive.
    Returns (n_results, prompt_with_marker_stripped); AUTO_N_RESULTS means
    the engine decides the count via score cutoff."""
    match = _MARKER_RE.search(prompt)
    if not match:
        return _env_n_results(), prompt
    cleaned = _MARKER_RE.sub("", prompt, count=1)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    value = match.group(1)
    return (AUTO_N_RESULTS if value.lower() == "auto" else int(value)), cleaned


def main() -> None:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    prompt = (payload.get("prompt") or "").strip()
    if len(prompt) < MIN_PROMPT_LENGTH:
        return

    n_results, query_text = _resolve_n_results(prompt)
    if n_results == 0:
        return

    cwd = Path(payload.get("cwd") or os.getcwd())

    logging.disable(logging.CRITICAL)
    try:
        from clawdiney.config import Config
        from clawdiney.query_engine import BrainQueryEngine

        vault = _detect_vault(cwd, Config.get_all_vaults())
        with BrainQueryEngine(vault=vault) as engine:
            result = engine.query(query_text, n_results=n_results, expand_graph=False)
    except Exception:
        return

    if not result.strip():
        return

    n_sources = result.count("--- Source")
    context_text = (
        "[clawdiney: contexto recuperado proativamente para este prompt — "
        "use search_brain/explore_graph/get_project_card para aprofundar]\n\n" + result
    )
    requested_note = (
        " (adaptive)" if n_results == AUTO_N_RESULTS else f" (n_results={n_results})"
    )
    print(
        json.dumps(
            {
                "systemMessage": (
                    f"🧠 clawdiney: {n_sources} fonte(s) injetada(s) no contexto{requested_note}"
                ),
                "hookSpecificOutput": {
                    "hookEventName": "UserPromptSubmit",
                    "additionalContext": context_text,
                },
            }
        )
    )


if __name__ == "__main__":
    main()
