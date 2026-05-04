import argparse
import os
import re
import sys
from pathlib import Path
from textwrap import dedent

from .config import Config
from .vault_config import load_vault_config


def main() -> None:
    parser = argparse.ArgumentParser(prog="clawdiney")
    subparsers = parser.add_subparsers(dest="command", required=True)
    vault_parser = subparsers.add_parser("vault", help="Manage vaults")
    vault_subparsers = vault_parser.add_subparsers(dest="vault_command", required=True)

    create = vault_subparsers.add_parser("create", help="Create a new vault")
    create.add_argument("id", type=str, help="Vault ID (letters, numbers, hyphens, underscores)")
    create.add_argument("--name", type=str, default=None, help="Display name")
    create.add_argument("--path", type=str, default=None, help="Path (default: VAULTS_DIR/id)")
    create.add_argument("--linked", type=str, default="", help="Comma-separated linked vault IDs")

    vault_subparsers.add_parser("list", help="List all configured vaults")
    args = parser.parse_args()

    if args.vault_command == "create":
        _vault_create(args)
    elif args.vault_command == "list":
        _vault_list()


def _validate_id(id_str: str) -> None:
    if not re.match(r"^[a-zA-Z0-9_-]+$", id_str):
        print("Error: Vault ID must contain only letters, numbers, hyphens, and underscores.", file=sys.stderr)
        sys.exit(1)


def _vault_create(args: argparse.Namespace) -> None:
    _validate_id(args.id)
    if args.path:
        vault_dir = Path(args.path)
    else:
        vaults_dir = os.getenv("VAULTS_DIR", "")
        if not vaults_dir:
            print("Error: Set VAULTS_DIR in .env or provide --path", file=sys.stderr)
            sys.exit(1)
        vault_dir = Path(vaults_dir) / args.id
    try:
        vault_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        print(f"Error: Directory already exists: {vault_dir}", file=sys.stderr)
        sys.exit(1)

    linked_ids = [v.strip() for v in args.linked.split(",") if v.strip()]
    name = args.name or args.id
    toml_content = dedent(f'''\
        id = "{args.id}"
        name = "{name}"
        description = ""
        linked_vaults = {linked_ids}
    ''')
    (vault_dir / "clawdiney.toml").write_text(toml_content)
    print(f"Vault '{args.id}' created at {vault_dir}")


def _vault_list() -> None:
    vaults = Config.get_all_vaults()
    if not vaults:
        print("No vaults configured")
        return
    print("Vaults:")
    for vid, vpath in vaults.items():
        try:
            config = load_vault_config(vpath)
            linked = ", ".join(config.linked_vaults) if config.linked_vaults else ""
            suffix = f"  linked: {linked}" if linked else ""
            print(f"  {vid:<12} {str(vpath):<20} {config.name:<20}{suffix}")
        except (ValueError, FileNotFoundError):
            print(f"  {vid:<12} {str(vpath):<20} {'<no config>':<20}")


if __name__ == "__main__":
    main()
