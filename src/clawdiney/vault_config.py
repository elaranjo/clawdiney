from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import List

import tomli


@dataclass
class VaultConfig:
    id: str
    name: str
    description: str = ""
    linked_vaults: List[str] = field(default_factory=list)
    include_patterns: List[str] = field(default_factory=list)
    exclude_patterns: List[str] = field(default_factory=list)


def load_vault_config(vault_root: Path) -> VaultConfig:
    toml_path = vault_root / "clawdiney.toml"
    if not toml_path.exists():
        raise ValueError(f"clawdiney.toml not found in {vault_root}")

    with toml_path.open("rb") as f:
        data = tomli.load(f)

    if "id" not in data:
        raise ValueError(f"Missing required field 'id' in {toml_path}")
    if "name" not in data:
        raise ValueError(f"Missing required field 'name' in {toml_path}")

    return VaultConfig(
        id=data["id"],
        name=data["name"],
        description=data.get("description", ""),
        linked_vaults=data.get("linked_vaults", []),
        include_patterns=data.get("include_patterns", []),
        exclude_patterns=data.get("exclude_patterns", []),
    )


def validate_linked_vaults(configs: dict[str, VaultConfig]) -> None:
    known_ids = set(configs.keys())

    for vault_id, config in configs.items():
        for linked_id in config.linked_vaults:
            if linked_id not in known_ids:
                raise ValueError(
                    f"Vault '{vault_id}' references linked_vault '{linked_id}' which does not exist"
                )

    WHITE = 0
    GRAY = 1
    BLACK = 2
    color: dict[str, int] = {vid: WHITE for vid in configs}

    def dfs(vault_id: str, path: list[str]) -> None:
        color[vault_id] = GRAY
        path.append(vault_id)
        for neighbor in configs[vault_id].linked_vaults:
            if neighbor not in configs:
                continue
            if color[neighbor] == GRAY:
                cycle_start = path.index(neighbor)
                cycle = path[cycle_start:] + [neighbor]
                raise ValueError(
                    f"Cycle detected in linked_vaults: {' → '.join(cycle)}"
                )
            if color[neighbor] == WHITE:
                dfs(neighbor, path)
        path.pop()
        color[vault_id] = BLACK

    for vault_id in configs:
        if color[vault_id] == WHITE:
            dfs(vault_id, [])
