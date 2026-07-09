"""
Automatic memory write path.

Normalizes a natural-language fact into (subject, predicate, value),
resolves the subject against existing entities using the same
embedding-similarity threshold as the project knowledge graph
(`Config.ENTITY_RESOLUTION_THRESHOLD`), and upserts it into a
provenance-marked note under `40_Memory/` — one note per resolved
subject, one bullet line per predicate.

This is the write-path counterpart to hybrid search: `write_memory`
is the only entry point that turns agent/conversation text into vault
content. Read-path tools (`search_brain`, `explore_graph`, ...) never
write.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal

from .config import Config
from .embedding_providers import EmbeddingProvider, default_provider
from .storage import KIND_CONCEPT, BrainStorage
from .vault_writer import VaultWriter

logger = logging.getLogger(__name__)

MEMORY_DIR = "40_Memory"

# Ordered longest-first so multi-word verbs (e.g. "works on") match before
# their single-word prefixes.
_PREDICATE_VERBS = sorted(
    [
        "prefers",
        "prefer",
        "is",
        "are",
        "was",
        "were",
        "has",
        "have",
        "uses",
        "use",
        "likes",
        "like",
        "wants",
        "want",
        "needs",
        "need",
        "works on",
        "owns",
        "dislikes",
        "dislike",
        "avoids",
        "avoid",
    ],
    key=len,
    reverse=True,
)

_SUBJECT_PREDICATE_RE = re.compile(
    r"^(?P<subject>[A-Z][\w' -]{0,60}?)\s+(?P<predicate>"
    + "|".join(re.escape(v) for v in _PREDICATE_VERBS)
    + r")\s+(?P<value>.+)$"
)

_FRONTMATTER_RE = re.compile(
    r"^---\n(?P<frontmatter>.*?)\n---\n(?P<body>.*)$", re.DOTALL
)
_CREATED_RE = re.compile(r"^created:\s*(.+)$", re.MULTILINE)


@dataclass
class NormalizedFact:
    """Result of parsing a raw fact string into subject/predicate/value.

    confidence is a heuristic: 1.0 when a known predicate verb was matched
    (grammatically confident split), 0.4 when we fell back to treating the
    whole sentence as a "mentions" fact about its leading words.
    """

    subject: str
    predicate: str
    value: str
    confidence: float
    raw: str


def normalize_fact(fact: str) -> NormalizedFact:
    """Parse "<Subject> <verb> <value>" out of a natural-language fact.

    Falls back to a low-confidence "mentions" fact (subject = first few
    words) when no known predicate verb is found — callers should gate on
    `confidence` before writing.
    """
    fact = fact.strip()
    if not fact:
        return NormalizedFact(
            subject="", predicate="", value="", confidence=0.0, raw=fact
        )

    match = _SUBJECT_PREDICATE_RE.match(fact)
    if match:
        return NormalizedFact(
            subject=match.group("subject").strip(),
            predicate=match.group("predicate").strip().lower(),
            value=match.group("value").strip().rstrip("."),
            confidence=1.0,
            raw=fact,
        )

    words = fact.split()
    subject = " ".join(words[:4]) if words else fact
    return NormalizedFact(
        subject=subject, predicate="mentions", value=fact, confidence=0.4, raw=fact
    )


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip()).strip("_")
    return slug or "unknown"


def _resolve_subject_entity(
    storage: BrainStorage,
    vault: str,
    subject: str,
    provider: EmbeddingProvider,
    threshold: float,
) -> str:
    """Return the canonical entity name for `subject` (existing or newly created)."""
    embedding = provider.embed(subject)
    hit = storage.find_similar_entity(vault, KIND_CONCEPT, embedding, threshold)
    if hit:
        logger.debug(
            "write_memory: resolved subject '%s' -> existing '%s' (%.2f)",
            subject,
            hit["name"],
            hit["similarity"],
        )
        return hit["name"]
    storage.upsert_typed_entity(vault, subject, KIND_CONCEPT, embedding=embedding)
    return subject


def _parse_note(content: str) -> tuple[str | None, str]:
    """Split an existing memory note into (created_at, body) — frontmatter dropped."""
    match = _FRONTMATTER_RE.match(content)
    if not match:
        return None, content
    frontmatter, body = match.group("frontmatter"), match.group("body")
    created_match = _CREATED_RE.search(frontmatter)
    return (created_match.group(1).strip() if created_match else None), body


def _bullet_pattern(predicate: str) -> re.Pattern[str]:
    return re.compile(
        rf"^- \*\*{re.escape(predicate)}\*\*: (?P<value>.+?) _\(source: .*?, agent: .*?, at: .*?\)_$",
        re.MULTILINE,
    )


def _upsert_bullet(
    body: str, predicate: str, value: str, source: str, agent_id: str, timestamp: str
) -> tuple[str, Literal["new", "updated", "unchanged"]]:
    """Insert or update the bullet line for `predicate` in `body`."""
    new_line = f"- **{predicate}**: {value} _(source: {source}, agent: {agent_id}, at: {timestamp})_"
    match = _bullet_pattern(predicate).search(body)
    if match:
        if match.group("value").strip() == value.strip():
            return body, "unchanged"
        return body[: match.start()] + new_line + body[match.end() :], "updated"

    if not body:
        return f"{new_line}\n", "new"
    prefix = body if body.endswith("\n") else body + "\n"
    return f"{prefix}{new_line}\n", "new"


def _build_frontmatter(subject: str, agent_id: str, created: str, updated: str) -> str:
    return (
        "---\n"
        "source: agent\n"
        f"agent_id: {agent_id}\n"
        f"subject: {subject}\n"
        f"created: {created}\n"
        f"updated: {updated}\n"
        "---\n"
    )


@dataclass
class MemoryWriteResult:
    success: bool
    path: str | None
    message: str
    subject: str | None = None
    predicate: str | None = None


def write_memory(
    fact: str,
    source: str,
    storage: BrainStorage,
    writer: VaultWriter,
    provider: EmbeddingProvider | None = None,
    vault: str = "default",
    agent_id: str = "default",
    min_confidence: float | None = None,
) -> MemoryWriteResult:
    """Normalize, resolve, and persist `fact` into a `40_Memory/` note.

    Read-only on failure: rejected/unchanged facts never touch the vault.
    """
    provider = provider or default_provider()
    min_confidence = (
        Config.MEMORY_MIN_CONFIDENCE if min_confidence is None else min_confidence
    )

    normalized = normalize_fact(fact)
    if not normalized.subject or not normalized.value:
        return MemoryWriteResult(
            success=False, path=None, message="Fact is empty or could not be parsed"
        )
    if normalized.confidence < min_confidence:
        return MemoryWriteResult(
            success=False,
            path=None,
            message=(
                f"Fact confidence {normalized.confidence:.2f} is below the minimum "
                f"{min_confidence:.2f}; rejected to avoid low-quality writes"
            ),
            subject=normalized.subject,
            predicate=normalized.predicate,
        )

    threshold = float(Config.ENTITY_RESOLUTION_THRESHOLD)
    entity_name = _resolve_subject_entity(
        storage, vault, normalized.subject, provider, threshold
    )

    note_path = f"{MEMORY_DIR}/{_slugify(entity_name)}.md"
    absolute_path = writer.vault_root / note_path
    existing_content = (
        absolute_path.read_text(encoding="utf-8") if absolute_path.is_file() else None
    )

    now = datetime.now(timezone.utc).isoformat()
    if existing_content is None:
        created, body = now, f"# {entity_name}\n\n"
    else:
        parsed_created, body = _parse_note(existing_content)
        created = parsed_created or now

    new_body, status = _upsert_bullet(
        body, normalized.predicate, normalized.value, source, agent_id, now
    )

    if status == "unchanged":
        return MemoryWriteResult(
            success=True,
            path=note_path,
            message="Fact already recorded (no-op)",
            subject=entity_name,
            predicate=normalized.predicate,
        )

    note_content = (
        _build_frontmatter(entity_name, agent_id, created, now) + "\n" + new_body
    )
    mode = "overwrite" if existing_content is not None else "create"
    result = writer.write_note(note_path, note_content, mode=mode)
    if not result["success"]:
        return MemoryWriteResult(
            success=False, path=note_path, message=result["message"]
        )

    return MemoryWriteResult(
        success=True,
        path=note_path,
        message="Fact updated" if status == "updated" else "Fact written",
        subject=entity_name,
        predicate=normalized.predicate,
    )
