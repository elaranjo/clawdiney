import argparse
import logging
import re
from pathlib import Path
from typing import Any, TypedDict

import chromadb
import ollama
from chromadb.utils.embedding_functions import EmbeddingFunction
from neo4j import GraphDatabase

from .chunking import Chunk, chunk_text
from .config import Config
from .constants import CHUNK_SIZE_DEFAULT, COLLECTION_PREFIX
from .logging_config import setup_logging

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


class OllamaEmbedding(EmbeddingFunction):
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or Config.MODEL_NAME
        self.ollama_client = ollama.Client(timeout=600)

    def __call__(self, input: list[str]) -> list[list[float]]:
        embeddings = []
        for text in input:
            response = self.ollama_client.embeddings(model=self.model_name, prompt=text)
            embeddings.append(response["embedding"])
        return embeddings

    def name(self) -> str:
        return f"ollama_{self.model_name}"


def create_chroma_client() -> chromadb.HttpClient:
    return chromadb.HttpClient(host=Config.CHROMA_HOST, port=Config.CHROMA_PORT)


def create_collection(
    client: chromadb.HttpClient, vault_name: str | None = None
) -> chromadb.Collection:
    name = f"{COLLECTION_PREFIX}{vault_name}" if vault_name else "obsidian_vault"
    return client.get_or_create_collection(
        name=name,
        embedding_function=OllamaEmbedding(model_name=Config.MODEL_NAME),
    )


def create_neo4j_driver() -> Any:
    return GraphDatabase.driver(
        Config.NEO4J_URI,
        auth=(Config.NEO4J_USER, Config.get_neo4j_password()),
    )


def extract_tags(content: str) -> list[str]:
    return sorted(set(re.findall(r"(?<!\w)#([A-Za-z0-9_/-]+)", content)))


def extract_wikilinks(content: str) -> list[str]:
    """Extract [[WikiLinks]] from content and return list of target names."""
    return re.findall(r"\[\[([^\]]+)\]\]", content)


def discover_vault_files(vault_root: Path) -> list[Path]:
    return sorted(vault_root.rglob("*.md"))


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


def build_chunk_payload(
    note_record: NoteRecord, vault_name: str = ""
) -> tuple[list[str], list[str], list[dict[str, Any]]]:
    ids = []
    documents = []
    metadatas: list[dict[str, Any]] = []

    for index, chunk in enumerate(note_record["chunks"]):
        metadata: dict[str, Any] = {
            "path": note_record["path"],
            "filename": note_record["name"],
            "header": chunk["header"],
            "source": note_record["source"],
            "chunk_index": index,
            "chunk_strategy": Config.CHUNKING_STRATEGY,
        }
        if vault_name:
            metadata["vault"] = vault_name
        if note_record["tags"]:
            metadata["tags"] = note_record["tags"]

        ids.append(f"{note_record['path']}::{index}")
        documents.append(
            f"File: {note_record['name']}\nPath: {note_record['path']}\nSection: {chunk['header']}\n\n{chunk['content']}"
        )
        metadatas.append(metadata)

    return ids, documents, metadatas


def index_note_records(
    collection: chromadb.Collection,
    note_records: list[NoteRecord],
    vault_name: str = "",
) -> int:
    indexed_chunks = 0

    for note_record in note_records:
        ids, documents, metadatas = build_chunk_payload(note_record, vault_name=vault_name)
        if not ids:
            continue
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        indexed_chunks += len(ids)

    return indexed_chunks


def sync_graph(
    neo4j_driver: Any,
    note_records: list[NoteRecord],
    incremental: bool = False,
    vault_name: str = "",
) -> None:
    """
    Sync notes to Neo4j graph with transactional guarantees.
    Uses pre-extracted wikilinks for O(n) link creation and Tag nodes for O(n) tag relationships.

    Schema:
    - (:Note)-[:LINKS_TO]->(:Note)  # WikiLinks entre notas
    - (:Note)-[:HAS_TAG]->(:Tag)    # Notas conectadas a nós Tag (O(n) ao invés de O(n²))

    Args:
        neo4j_driver: Neo4j driver instance
        note_records: List of note records to sync
        incremental: If True, only update relationships for the given notes (O(1) per note).
                     If False, rebuilds all relationships (O(n) total, use for full sync).
    """
    with neo4j_driver.session() as session:
        tx = session.begin_transaction()
        try:
            # 1. Create/update all note nodes
            tx.run(
                """
                UNWIND $files AS file
                MERGE (n:Note {path: file.path, vault: file.vault})
                SET n.name = file.name,
                    n.content = file.content,
                    n.last_indexed = timestamp(),
                    n.tags = file.tags
                """,
                files=[
                    {
                        "name": note["name"],
                        "path": note["path"],
                        "content": note["content"],
                        "tags": note["tags"],
                        "vault": vault_name,
                    }
                    for note in note_records
                ],
            )

            if incremental:
                # 2a. INCREMENTAL MODE: Delete only relationships for the synced notes
                paths = [note["path"] for note in note_records]
                tx.run(
                    "MATCH (n:Note) WHERE n.path IN $paths MATCH ()-[r:LINKS_TO]->(n) DELETE r",
                    paths=paths,
                )
                tx.run(
                    "MATCH (n:Note) WHERE n.path IN $paths MATCH (n)-[r:LINKS_TO]->() DELETE r",
                    paths=paths,
                )
                tx.run(
                    "MATCH (n:Note) WHERE n.path IN $paths MATCH (n)-[r:HAS_TAG]->() DELETE r",
                    paths=paths,
                )
            else:
                # 2b. FULL SYNC MODE: Delete relationships and orphan Tag nodes
                if vault_name:
                    tx.run(
                        "MATCH (n:Note {vault: $vault_name})-[r:LINKS_TO|HAS_TAG]->() DELETE r",
                        vault_name=vault_name,
                    )
                else:
                    tx.run("MATCH ()-[r:LINKS_TO|HAS_TAG]->() DELETE r")
                tx.run("MATCH (t:Tag) WHERE NOT (t)<-[:HAS_TAG]-() DELETE t")

            # 3. Create LINKS_TO relationships using pre-extracted wikilinks (O(n))
            links_data = []
            for note in note_records:
                for link_target in note["wikilinks"]:
                    links_data.append(
                        {
                            "source_path": note["path"],
                            "target_name": link_target,
                        }
                    )

            if links_data:
                tx.run(
                    """
                    UNWIND $links AS link
                    MATCH (source:Note {path: link.source_path})
                    MATCH (target:Note)
                    WHERE target.path = link.target_name OR target.name = link.target_name
                    MERGE (source)-[:LINKS_TO]->(target)
                    """,
                    links=links_data,
                )

            # 4. Create Tag nodes and HAS_TAG relationships (O(n) total)
            # Collect all tags with their notes
            tags_to_notes: dict[str, list[str]] = {}
            for note in note_records:
                for tag in note["tags"]:
                    if tag not in tags_to_notes:
                        tags_to_notes[tag] = []
                    tags_to_notes[tag].append(note["path"])

            # Create Tag nodes and relationships
            tag_data = [
                {"tag": tag, "note_paths": paths}
                for tag, paths in tags_to_notes.items()
            ]

            if tag_data:
                tx.run(
                    """
                    UNWIND $tags AS tag_info
                    MERGE (t:Tag {name: tag_info.tag})
                    WITH t, tag_info
                    UNWIND tag_info.note_paths AS note_path
                    MATCH (n:Note {path: note_path})
                    MERGE (n)-[:HAS_TAG]->(t)
                    """,
                    {"tags": tag_data},
                )

            tx.commit()
        except Exception as e:
            tx.rollback()
            raise RuntimeError(f"Failed to sync graph: {e}") from e


def index_vault(
    vault_root: Path | str | None = None,
    collection: chromadb.Collection | None = None,
    neo4j_driver: Any | None = None,
    strategy: str | None = None,
) -> dict[str, Any]:
    return _index_vault_inner(
        vault_root=vault_root,
        collection=collection,
        neo4j_driver=neo4j_driver,
        strategy=strategy,
        vault_name="",
    )


def _index_vault_inner(
    vault_root: Path | str | None = None,
    collection: chromadb.Collection | None = None,
    neo4j_driver: Any | None = None,
    strategy: str | None = None,
    vault_name: str = "",
) -> dict[str, Any]:
    vault_root = Path(vault_root or Config.VAULT_PATH).expanduser().resolve()
    own_collection = collection is None
    own_driver = neo4j_driver is None

    if own_collection:
        collection = create_collection(
            create_chroma_client(), vault_name=vault_name or None
        )
    if own_driver:
        neo4j_driver = create_neo4j_driver()

    total_files = 0
    processed_files = 0
    note_records: list[NoteRecord] = []

    try:
        for file_path in discover_vault_files(vault_root):
            total_files += 1
            try:
                note_record = build_note_record(
                    file_path, vault_root, strategy=strategy
                )
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
            collection, note_records, vault_name=vault_name
        )
        sync_graph(
            neo4j_driver, note_records, vault_name=vault_name
        )

        return {
            "vault_root": str(vault_root),
            "total_files": total_files,
            "processed_files": processed_files,
            "indexed_chunks": indexed_chunks,
            "vault_name": vault_name or None,
        }
    finally:
        if own_driver and neo4j_driver is not None:
            neo4j_driver.close()


def index_named_vault(
    vault_name: str,
    collection: chromadb.Collection | None = None,
    neo4j_driver: Any | None = None,
    strategy: str | None = None,
) -> dict[str, Any]:
    vault_path = Config.get_vault_path(vault_name)
    return _index_vault_inner(
        vault_root=vault_path,
        collection=collection,
        neo4j_driver=neo4j_driver,
        strategy=strategy,
        vault_name=vault_name,
    )


def index_all_vaults(
    collection: chromadb.Collection | None = None,
    neo4j_driver: Any | None = None,
    strategy: str | None = None,
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    for vault_name, vault_path in Config.get_all_vaults().items():
        logger.info(f"Indexing vault '{vault_name}' from {vault_path}")
        results[vault_name] = index_named_vault(
            vault_name,
            collection=collection,
            neo4j_driver=neo4j_driver,
            strategy=strategy,
        )
    return results


def main() -> dict[str, Any] | dict[str, dict[str, Any]]:
    setup_logging()
    parser = argparse.ArgumentParser(description="Index Obsidian vault(s) into ChromaDB and Neo4j")
    parser.add_argument("--vault", type=str, default=None, help="Index only a specific vault by name")
    args = parser.parse_args()

    if args.vault:
        logger.info(f"Indexing vault '{args.vault}' from {Config.get_vault_path(args.vault)}")
        summary = index_named_vault(args.vault)
        logger.info(
            f"Indexing complete: {summary['processed_files']}/{summary['total_files']} files processed, "
            f"{summary['indexed_chunks']} chunks indexed"
        )
    elif Config._is_multi_vault():
        logger.info(f"Indexing all configured vaults: {list(Config.get_all_vaults().keys())}")
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
