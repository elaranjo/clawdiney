"""
Full vault indexing into the embedded SQLite store (brain.db).

Parses Obsidian notes, chunks them, embeds via the configured
EmbeddingProvider, and writes chunks/vectors/FTS/graph rows through
BrainStorage — one transaction per note.
"""

import argparse
import hashlib
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, TypedDict

from .chunking import Chunk, chunk_text
from .config import Config
from .constants import CHUNK_SIZE_DEFAULT
from .embedding_providers import EmbeddingProvider, default_provider
from .logging_config import setup_logging
from .storage import BrainStorage, get_storage

logger = logging.getLogger(__name__)


class NoteRecord(TypedDict):
    """Represents an indexed note with all metadata."""

    name: str
    path: str
    source: str
    content: str
    tags: list[str]
    wikilinks: list[str]
    chunks: list[Chunk]


def extract_tags(content: str) -> list[str]:
    return sorted(set(re.findall(r"(?<!\w)#([A-Za-z0-9_/-]+)", content)))


def extract_wikilinks(content: str) -> list[str]:
    """Extract [[WikiLinks]] from content and return list of target names."""
    targets = []
    for raw in re.findall(r"\[\[([^\]]+)\]\]", content):
        # Strip alias ([[Target|Alias]]) and heading anchors ([[Target#Section]])
        target = raw.split("|")[0].split("#")[0].strip()
        if target:
            targets.append(target)
    return targets


def discover_vault_files(vault_root: Path) -> list[Path]:
    return sorted(vault_root.rglob("*.md"))


def compute_content_hash(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def build_note_record(
    file_path: Path, vault_root: Path, strategy: str | None = None
) -> NoteRecord | None:
    content = file_path.read_text(encoding="utf-8")
    if not content.strip():
        return None

    relative_path = file_path.relative_to(vault_root).as_posix()
    tags = extract_tags(content)
    wikilinks = extract_wikilinks(content)
    chunks = chunk_text(content, strategy=strategy, chunk_size=CHUNK_SIZE_DEFAULT)

    return {
        "name": file_path.name,
        "path": relative_path,
        "source": str(file_path),
        "content": content,
        "tags": tags,
        "wikilinks": wikilinks,
        "chunks": chunks,
    }


def build_chunk_documents(note_record: NoteRecord) -> list[str]:
    """Text sent to the embedder: contextualized with file/section headers."""
    return [
        f"File: {note_record['name']}\n"
        f"Path: {note_record['path']}\n"
        f"Section: {chunk['header']}\n\n{chunk['content']}"
        for chunk in note_record["chunks"]
    ]


def index_note(
    storage: BrainStorage,
    provider: EmbeddingProvider,
    note_record: NoteRecord,
    vault_name: str = "default",
    agent_id: str = "default",
) -> int:
    """Embed and persist one note atomically. Returns chunks indexed."""
    documents = build_chunk_documents(note_record)
    embeddings = provider.embed_batch(documents) if documents else []
    chunk_rows = [
        {"header": chunk["header"], "content": doc}
        for chunk, doc in zip(note_record["chunks"], documents)
    ]
    return storage.upsert_note(
        vault=vault_name,
        path=note_record["path"],
        content_hash=compute_content_hash(note_record["content"].encode("utf-8")),
        updated_at=datetime.now().isoformat(),
        chunks=chunk_rows,
        embeddings=embeddings,
        wikilinks=note_record["wikilinks"],
        tags=note_record["tags"],
        name=note_record["name"],
        agent_id=agent_id,
    )


def index_note_records(
    storage: BrainStorage,
    note_records: list[NoteRecord],
    vault_name: str = "default",
    provider: EmbeddingProvider | None = None,
) -> int:
    provider = provider or default_provider()
    indexed_chunks = 0
    for note_record in note_records:
        indexed_chunks += index_note(
            storage, provider, note_record, vault_name=vault_name
        )
    return indexed_chunks


def _index_vault_inner(
    vault_root: Path | str | None = None,
    storage: BrainStorage | None = None,
    strategy: str | None = None,
    vault_name: str = "default",
    provider: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    vault_root = Path(vault_root or Config.VAULT_PATH).expanduser().resolve()
    storage = storage or get_storage()
    provider = provider or default_provider()

    total_files = 0
    processed_files = 0
    note_records: list[NoteRecord] = []

    for file_path in discover_vault_files(vault_root):
        total_files += 1
        try:
            note_record = build_note_record(file_path, vault_root, strategy=strategy)
            if note_record is None:
                logger.warning(f"Skipping empty file: {file_path.name}")
                continue
            note_records.append(note_record)
            processed_files += 1
            logger.debug(
                f"Processed: {note_record['path']} ({len(note_record['chunks'])} chunks)"
            )
        except Exception as exc:
            logger.error(f"Error processing {file_path}: {exc}")

    indexed_chunks = index_note_records(
        storage, note_records, vault_name=vault_name, provider=provider
    )

    return {
        "vault_root": str(vault_root),
        "total_files": total_files,
        "processed_files": processed_files,
        "indexed_chunks": indexed_chunks,
        "vault_name": vault_name,
    }


def index_vault(
    vault_root: Path | str | None = None,
    storage: BrainStorage | None = None,
    strategy: str | None = None,
    provider: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    return _index_vault_inner(
        vault_root=vault_root,
        storage=storage,
        strategy=strategy,
        vault_name="default",
        provider=provider,
    )


def index_named_vault(
    vault_name: str,
    storage: BrainStorage | None = None,
    strategy: str | None = None,
    provider: EmbeddingProvider | None = None,
) -> dict[str, Any]:
    vault_path = Config.get_vault_path(vault_name)
    return _index_vault_inner(
        vault_root=vault_path,
        storage=storage,
        strategy=strategy,
        vault_name=vault_name,
        provider=provider,
    )


def index_all_vaults(
    storage: BrainStorage | None = None,
    strategy: str | None = None,
    provider: EmbeddingProvider | None = None,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for vault_name, vault_path in Config.get_all_vaults().items():
        logger.info(f"Indexing vault '{vault_name}' from {vault_path}")
        results[vault_name] = index_named_vault(
            vault_name, storage=storage, strategy=strategy, provider=provider
        )
    return results


def main() -> dict[str, Any] | dict[str, dict[str, Any]]:
    setup_logging()
    parser = argparse.ArgumentParser(
        description="Index Obsidian vault(s) into the embedded brain.db"
    )
    parser.add_argument(
        "--vault", type=str, default=None, help="Index only a specific vault by name"
    )
    args = parser.parse_args()

    if args.vault:
        logger.info(
            f"Indexing vault '{args.vault}' from {Config.get_vault_path(args.vault)}"
        )
        summary = index_named_vault(args.vault)
        logger.info(
            f"Indexing complete: {summary['processed_files']}/{summary['total_files']} files processed, "
            f"{summary['indexed_chunks']} chunks indexed"
        )
    elif Config._is_multi_vault():
        logger.info(
            f"Indexing all configured vaults: {list(Config.get_all_vaults().keys())}"
        )
        summaries = index_all_vaults()
        total_all = sum(s["indexed_chunks"] for s in summaries.values())
        logger.info(f"All vaults indexed: {total_all} total chunks indexed")
        return summaries
    else:
        logger.info(f"Starting indexing of files from {Config.VAULT_PATH}")
        summary = _index_vault_inner()
        logger.info(
            f"Indexing complete: {summary['processed_files']}/{summary['total_files']} files processed, "
            f"{summary['indexed_chunks']} chunks indexed"
        )
    return summary


if __name__ == "__main__":
    main()
