#!/usr/bin/env python3
"""
Safely register the Clawdiney MCP server in ~/.claude.json.

Merges (never overwrites) the target file: only
`.projects[<projects_dir>].mcpServers.clawdiney` is added or replaced.
Everything else in the file — other projects, other MCP servers, unrelated
settings — is left untouched. A timestamped backup is written before any
change, and the user is shown the exact JSON that will be written and must
confirm before it's saved.
"""

import argparse
import copy
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path


def build_entry(python_bin: str, vaults_dir: str) -> dict:
    return {
        "command": python_bin,
        "args": ["-m", "clawdiney.mcp_server"],
        "env": {
            "VAULTS_DIR": vaults_dir,
            "MCP_DEFAULT_VAULT": "general",
            "MODEL_NAME": "bge-m3:latest",
            "ENABLE_RERANK": "true",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claude-config", required=True)
    parser.add_argument("--projects-dir", required=True)
    parser.add_argument("--python-bin", required=True)
    parser.add_argument("--vaults-dir", required=True)
    args = parser.parse_args()

    config_path = Path(args.claude_config).expanduser()
    if not config_path.exists():
        print(f"❌ {config_path} not found.", file=sys.stderr)
        return 1

    try:
        original = json.loads(config_path.read_text())
    except json.JSONDecodeError as exc:
        print(f"❌ {config_path} is not valid JSON: {exc}", file=sys.stderr)
        return 1

    updated = copy.deepcopy(original)
    updated.setdefault("projects", {})
    project_key = args.projects_dir
    updated["projects"].setdefault(project_key, {})
    updated["projects"][project_key].setdefault("mcpServers", {})

    before = updated["projects"][project_key]["mcpServers"].get("clawdiney")
    after = build_entry(args.python_bin, args.vaults_dir)

    if before == after:
        print("✅ Claude Code is already configured for clawdiney. Nothing to do.")
        return 0

    updated["projects"][project_key]["mcpServers"]["clawdiney"] = after

    print("--- Will write this MCP server entry ---")
    print(json.dumps({"clawdiney": after}, indent=2, ensure_ascii=False))
    print("-----------------------------------------")
    reply = input("Apply this change to your Claude config? (y/n): ").strip().lower()
    if reply not in ("y", "yes"):
        print("Skipped. No changes made.")
        return 0

    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = config_path.with_suffix(f".json.bak.{timestamp}")
    shutil.copy2(config_path, backup_path)

    config_path.write_text(json.dumps(updated, indent=2, ensure_ascii=False) + "\n")

    print(f"✅ Backup saved to {backup_path}")
    print(f'✅ Registered clawdiney MCP server under projects["{project_key}"]')
    print("   Restart Claude Code sessions in that directory for it to take effect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
