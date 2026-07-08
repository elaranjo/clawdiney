"""
Two-layer entity extraction for the project knowledge graph.

Layer 1 (deterministic, confidence 1.0): parses project manifests
(pyproject.toml, package.json, docker-compose.yml, .env.example) into
typed entities and relations, plus the Interfaces data used by project
cards.

Layer 2 (semantic, confidence < 1.0): LLM extraction over the project
card via Ollama structured JSON output, with embedding-based entity
resolution to avoid duplicates. Gated by card content hash.
"""

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import tomli

from .config import Config
from .storage import (
    KIND_CONCEPT,
    KIND_DATASTORE,
    KIND_LIBRARY,
    KIND_PATTERN,
    KIND_SERVICE,
    REL_CALLS_API_OF,
    REL_DEPENDS_ON,
    REL_IMPLEMENTS,
    REL_MENTIONS,
    REL_SHARES_DB,
    REL_USES_PATTERN,
    BrainStorage,
)

logger = logging.getLogger(__name__)

SEMANTIC_KINDS = {
    KIND_SERVICE,
    KIND_LIBRARY,
    KIND_PATTERN,
    KIND_DATASTORE,
    KIND_CONCEPT,
}
SEMANTIC_REL_TYPES = {REL_USES_PATTERN, REL_IMPLEMENTS, REL_MENTIONS, REL_CALLS_API_OF}

DATASTORE_SCHEMES = {
    "postgres": "postgresql",
    "postgresql": "postgresql",
    "mysql": "mysql",
    "mongodb": "mongodb",
    "redis": "redis",
    "bolt": "neo4j",
    "neo4j": "neo4j",
    "sqlite": "sqlite",
    "amqp": "rabbitmq",
}

_URL_RE = re.compile(r"\b([a-z][a-z0-9+]*)://([^\s\"'@/]*@)?([^\s\"'/:]+)(:\d+)?", re.I)
_PORT_LITERAL_RE = re.compile(r"port\s*[=:]\s*(\d{2,5})", re.I)


@dataclass
class ExtractedEntity:
    name: str
    kind: str
    description: str = ""
    source_file: str = ""


@dataclass
class ExtractedRelation:
    target_name: str
    target_kind: str
    rel_type: str
    confidence: float = 1.0
    source_file: str = ""
    quote: str | None = None


@dataclass
class Interfaces:
    exposes: list[tuple[str, str]] = field(default_factory=list)  # (desc, source)
    consumes: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Layer1Result:
    entities: list[ExtractedEntity] = field(default_factory=list)
    relations: list[ExtractedRelation] = field(default_factory=list)
    interfaces: Interfaces = field(default_factory=Interfaces)


# ---------------------------------------------------------------------------
# Layer 1: deterministic manifest parsing
# ---------------------------------------------------------------------------


def _dep_name(spec: str) -> str:
    """'httpx>=0.25.0' -> 'httpx'; '@scope/pkg' preserved."""
    return re.split(r"[<>=!~\[; ]", spec.strip(), maxsplit=1)[0]


def _parse_pyproject(path: Path, result: Layer1Result) -> None:
    with open(path, "rb") as f:
        data = tomli.load(f)
    project = data.get("project", {})
    for spec in project.get("dependencies", []):
        name = _dep_name(spec)
        if name:
            result.entities.append(
                ExtractedEntity(name, KIND_LIBRARY, source_file=path.name)
            )
            result.relations.append(
                ExtractedRelation(name, KIND_LIBRARY, REL_DEPENDS_ON, 1.0, path.name)
            )
    for script, target in project.get("scripts", {}).items():
        result.interfaces.exposes.append((f"CLI: `{script}` ({target})", path.name))


def _parse_package_json(path: Path, result: Layer1Result) -> None:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    for name in data.get("dependencies", {}):
        result.entities.append(
            ExtractedEntity(name, KIND_LIBRARY, source_file=path.name)
        )
        result.relations.append(
            ExtractedRelation(name, KIND_LIBRARY, REL_DEPENDS_ON, 1.0, path.name)
        )
    for script in data.get("scripts", {}):
        result.interfaces.exposes.append((f"npm script: `{script}`", path.name))
    bin_field = data.get("bin")
    if isinstance(bin_field, dict):
        for name in bin_field:
            result.interfaces.exposes.append((f"CLI: `{name}`", path.name))


def _parse_compose(path: Path, result: Layer1Result) -> None:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError:
        logger.warning("PyYAML not installed; skipping %s", path)
        return
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    for svc_name, svc in (data.get("services") or {}).items():
        if not isinstance(svc, dict):
            continue
        image = str(svc.get("image", ""))
        image_base = image.split(":")[0].rsplit("/", 1)[-1]
        kind = KIND_DATASTORE if image_base in DATASTORE_SCHEMES else KIND_SERVICE
        rel = REL_SHARES_DB if kind == KIND_DATASTORE else REL_CALLS_API_OF
        result.entities.append(
            ExtractedEntity(svc_name, kind, description=image, source_file=path.name)
        )
        result.relations.append(ExtractedRelation(svc_name, kind, rel, 1.0, path.name))
        for port in svc.get("ports") or []:
            result.interfaces.exposes.append(
                (f"service `{svc_name}` port {port}", path.name)
            )


def _parse_env_example(path: Path, result: Layer1Result) -> None:
    text = path.read_text(encoding="utf-8", errors="replace")
    for match in _URL_RE.finditer(text):
        scheme = match.group(1).lower()
        host = match.group(3)
        if scheme in DATASTORE_SCHEMES:
            name = DATASTORE_SCHEMES[scheme]
            result.entities.append(
                ExtractedEntity(
                    name,
                    KIND_DATASTORE,
                    description=f"{scheme}://{host}",
                    source_file=path.name,
                )
            )
            result.relations.append(
                ExtractedRelation(name, KIND_DATASTORE, REL_SHARES_DB, 1.0, path.name)
            )
            result.interfaces.consumes.append(
                (f"{name} ({scheme}://{host})", path.name)
            )
        elif scheme in ("http", "https"):
            result.interfaces.consumes.append((f"HTTP service {host}", path.name))


_MANIFEST_PARSERS = {
    "pyproject.toml": _parse_pyproject,
    "package.json": _parse_package_json,
    "docker-compose.yml": _parse_compose,
    "docker-compose.yaml": _parse_compose,
    ".env.example": _parse_env_example,
}


def extract_from_manifests(project_path: Path) -> Layer1Result:
    """Layer 1: deterministic entities/relations/interfaces from manifests."""
    result = Layer1Result()
    for filename, parser in _MANIFEST_PARSERS.items():
        manifest = project_path / filename
        if not manifest.exists():
            continue
        try:
            parser(manifest, result)
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", manifest, exc)
    _detect_exposed_ports(project_path, result)
    _dedupe(result)
    return result


def _detect_exposed_ports(project_path: Path, result: Layer1Result) -> None:
    """Port literals in likely entry files (scoped, not a tree scan)."""
    candidates = [
        "main.py",
        "app.py",
        "src/main.py",
        "src/app.py",
        "index.js",
        "src/index.js",
        "src/index.ts",
    ]
    for rel in candidates:
        entry = project_path / rel
        if not entry.is_file():
            continue
        try:
            text = entry.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for match in _PORT_LITERAL_RE.finditer(text):
            result.interfaces.exposes.append((f"port {match.group(1)}", rel))


def _dedupe(result: Layer1Result) -> None:
    seen_e: set[tuple[str, str]] = set()
    entities = []
    for entity in result.entities:
        key = (entity.name, entity.kind)
        if key not in seen_e:
            seen_e.add(key)
            entities.append(entity)
    result.entities = entities

    seen_r: set[tuple[str, str, str]] = set()
    relations = []
    for rel in result.relations:
        rel_key = (rel.target_name, rel.target_kind, rel.rel_type)
        if rel_key not in seen_r:
            seen_r.add(rel_key)
            relations.append(rel)
    result.relations = relations

    result.interfaces.exposes = list(dict.fromkeys(result.interfaces.exposes))
    result.interfaces.consumes = list(dict.fromkeys(result.interfaces.consumes))


# ---------------------------------------------------------------------------
# Layer 2: LLM semantic extraction
# ---------------------------------------------------------------------------

_EXTRACTION_PROMPT = """You are extracting a knowledge graph from a software project card.
Return ONLY JSON with this exact shape:
{{"entities": [{{"name": str, "kind": str, "description": str}}],
  "relations": [{{"target": str, "rel_type": str, "confidence": float, "quote": str}}]}}

Rules:
- kind must be one of: service, library, pattern, datastore, concept
- rel_type must be one of: USES_PATTERN, IMPLEMENTS, MENTIONS, CALLS_API_OF
- relations are FROM the project "{project}" TO the named target entity
- confidence: your certainty in (0, 1)
- quote: short verbatim excerpt from the card supporting the relation
- extract only what the card states; do not invent

PROJECT CARD:
{card}
"""


def extract_semantic(
    card_content: str,
    project_name: str,
    model: str | None = None,
    client: Any = None,
) -> tuple[list[ExtractedEntity], list[ExtractedRelation]]:
    """LLM extraction over a project card. Invalid items dropped with warning."""
    if client is None:
        import ollama

        client = ollama.Client()
    model = model or Config.CARD_LLM_MODEL

    response = client.generate(
        model=model,
        prompt=_EXTRACTION_PROMPT.format(project=project_name, card=card_content),
        format="json",
        options={"temperature": 0},
    )
    raw = response.get("response", "")
    raw = re.sub(r"^```(json)?|```$", "", raw.strip(), flags=re.M).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Semantic extraction returned invalid JSON: %s", exc)
        return [], []

    entities: list[ExtractedEntity] = []
    by_name: dict[str, str] = {}
    for item in data.get("entities", []) or []:
        try:
            name = str(item["name"]).strip()
            kind = str(item["kind"]).strip()
        except (KeyError, TypeError):
            logger.warning("Dropping malformed entity: %r", item)
            continue
        if not name or kind not in SEMANTIC_KINDS:
            logger.warning("Dropping entity with invalid kind: %r", item)
            continue
        entities.append(ExtractedEntity(name, kind, str(item.get("description", ""))))
        by_name[name] = kind

    relations: list[ExtractedRelation] = []
    for item in data.get("relations", []) or []:
        try:
            target = str(item["target"]).strip()
            rel_type = str(item["rel_type"]).strip()
            confidence = float(item.get("confidence", 0.5))
        except (KeyError, TypeError, ValueError):
            logger.warning("Dropping malformed relation: %r", item)
            continue
        if not target or rel_type not in SEMANTIC_REL_TYPES:
            logger.warning("Dropping relation with invalid type: %r", item)
            continue
        confidence = min(max(confidence, 0.1), 0.99)
        relations.append(
            ExtractedRelation(
                target_name=target,
                target_kind=by_name.get(target, KIND_CONCEPT),
                rel_type=rel_type,
                confidence=confidence,
                quote=str(item.get("quote", "")) or None,
            )
        )
    return entities, relations


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def _resolve_entity_id(
    storage: BrainStorage,
    vault: str,
    entity: ExtractedEntity,
    provider: Any,
    threshold: float,
) -> int:
    """Entity resolution: reuse similar existing entity or insert with vector."""
    embedding = provider.embed(f"{entity.name}: {entity.description}".strip(": "))
    hit = storage.find_similar_entity(vault, entity.kind, embedding, threshold)
    if hit:
        logger.debug(
            "Resolved '%s' -> existing '%s' (%.2f)",
            entity.name,
            hit["name"],
            hit["similarity"],
        )
        return hit["id"]
    return storage.upsert_typed_entity(
        vault, entity.name, entity.kind, entity.description, embedding=embedding
    )


def extract_for_project_card(
    project_name: str,
    project_path: Path,
    card_file: Path,
    vault_root: Path,
) -> dict[str, Any] | None:
    """
    Convenience wrapper for watcher/CLI: run both layers for a project whose
    card was just written into a vault. Never raises (logs and returns None).
    """
    try:
        from .storage import get_storage

        vault_root = vault_root.resolve()
        vault_name = next(
            (
                vid
                for vid, vpath in Config.get_all_vaults().items()
                if Path(vpath).expanduser().resolve() == vault_root
            ),
            "default",
        )
        card_content = card_file.read_text(encoding="utf-8", errors="replace")
        card_rel = card_file.resolve().relative_to(vault_root).as_posix()
        return run_extraction(
            project_name,
            project_path,
            get_storage(),
            vault=vault_name,
            card_path=card_rel,
            card_content=card_content,
        )
    except Exception as exc:
        logger.warning("Graph extraction failed for '%s': %s", project_name, exc)
        return None


def run_extraction(
    project_name: str,
    project_path: Path,
    storage: BrainStorage,
    vault: str = "default",
    provider: Any = None,
    card_path: str | None = None,
    card_content: str | None = None,
    llm_client: Any = None,
) -> dict[str, Any]:
    """
    Run both extraction layers for a project.

    Layer 1 always runs (deterministic, cheap). Layer 2 runs only when
    card_content is provided and its hash changed since the last run.
    Returns summary counts.
    """
    summary: dict[str, Any] = {"project": project_name, "layer1": 0, "layer2": 0}

    # --- Layer 1 ---
    layer1 = extract_from_manifests(project_path)
    entity_ids: dict[tuple[str, str], int] = {}
    for entity in layer1.entities:
        entity_ids[(entity.name, entity.kind)] = storage.upsert_typed_entity(
            vault, entity.name, entity.kind, entity.description or None
        )
    det_relations = [
        {
            "target_id": entity_ids[(rel.target_name, rel.target_kind)],
            "rel_type": rel.rel_type,
            "confidence": 1.0,
        }
        for rel in layer1.relations
        if (rel.target_name, rel.target_kind) in entity_ids
    ]
    summary["layer1"] = storage.replace_project_relations(
        vault, project_name, "deterministic", det_relations
    )

    # --- Layer 2 ---
    if card_content is None:
        return summary

    card_hash = hashlib.sha256(card_content.encode("utf-8")).hexdigest()
    hash_key = f"extract_hash:{vault}:{project_name}"
    if storage.get_meta(hash_key) == card_hash:
        logger.debug("Card unchanged for '%s'; skipping semantic layer", project_name)
        summary["layer2"] = "skipped"
        return summary

    if provider is None:
        from .embedding_providers import default_provider

        provider = default_provider()

    try:
        sem_entities, sem_relations = extract_semantic(
            card_content, project_name, client=llm_client
        )
    except Exception as exc:
        logger.warning("Semantic extraction failed for '%s': %s", project_name, exc)
        return summary

    threshold = float(Config.ENTITY_RESOLUTION_THRESHOLD)
    resolved: dict[str, int] = {}
    for entity in sem_entities:
        resolved[entity.name] = _resolve_entity_id(
            storage, vault, entity, provider, threshold
        )

    rel_rows = []
    for rel in sem_relations:
        target_id = resolved.get(rel.target_name)
        if target_id is None:
            target_id = _resolve_entity_id(
                storage,
                vault,
                ExtractedEntity(rel.target_name, rel.target_kind),
                provider,
                threshold,
            )
        evidence_id = (
            storage.find_chunk_by_quote(vault, card_path, rel.quote)
            if (card_path and rel.quote)
            else None
        )
        rel_rows.append(
            {
                "target_id": target_id,
                "rel_type": rel.rel_type,
                "confidence": rel.confidence,
                "evidence_chunk_id": evidence_id,
            }
        )
    summary["layer2"] = storage.replace_project_relations(
        vault, project_name, "semantic", rel_rows
    )
    storage.set_meta(hash_key, card_hash)
    return summary
