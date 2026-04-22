import logging
import re
from pathlib import Path
from typing import Any, TypedDict

import chromadb
import ollama
from chromadb.utils.embedding_functions import EmbeddingFunction
from neo4j import GraphDatabase

from chunking import Chunk, chunk_text
from config import Config
from logging_config import setup_logging

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


def create_collection(client: chromadb.HttpClient) -> chromadb.Collection:
    return client.get_or_create_collection(
        name="obsidian_vault",
        embedding_function=OllamaEmbedding(model_name=Config.MODEL_NAME),
    )


def create_neo4j_driver() -> Any:
    return GraphDatabase.driver(
        Config.NEO4J_URI,
        auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD),
    )


def extract_tags(content: str) -> list[str]:
    return sorted(set(re.findall(r"(?<!\w)#([A-Za-z0-9_/-]+)", content)))


def extract_wikilinks(content: str) -> list[str]:
    """Extract [[WikiLinks]] from content and return list of target names."""
    return re.findall(r'\[\[([^\]]+)\]\]', content)


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
    chunks = chunk_text(content, strategy=strategy)

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
    note_record: NoteRecord,
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
        if note_record["tags"]:
            metadata["tags"] = note_record["tags"]

        ids.append(f"{note_record['path']}::{index}")
        documents.append(
            f"File: {note_record['name']}\nPath: {note_record['path']}\nSection: {chunk['header']}\n\n{chunk['content']}"
        )
        metadatas.append(metadata)

    return ids, documents, metadatas


def index_note_records(
    collection: chromadb.Collection, note_records: list[NoteRecord]
) -> int:
    indexed_chunks = 0

    for note_record in note_records:
        ids, documents, metadatas = build_chunk_payload(note_record)
        if not ids:
            continue
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        indexed_chunks += len(ids)

    return indexed_chunks


def sync_graph(neo4j_driver: Any, note_records: list[NoteRecord]) -> None:
    """
    Sync notes to Neo4j graph with transactional guarantees.
    Uses pre-extracted wikilinks for O(n) link creation instead of O(n²) cartesian join.
    """
    with neo4j_driver.session() as session:
        tx = session.begin_transaction()
        try:
            # 1. Create/update all note nodes
            tx.run(
                """
                UNWIND $files AS file
                MERGE (n:Note {path: file.path})
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
                    }
                    for note in note_records
                ],
            )

            # 2. Delete old relationships (not nodes)
            tx.run("MATCH ()-[r:LINKS_TO|SHARES_TAG]->() DELETE r")

            # 3. Create LINKS_TO relationships using pre-extracted wikilinks (O(n))
            links_data = []
            for note in note_records:
                for link_target in note["wikilinks"]:
                    links_data.append({
                        "source_path": note["path"],
                        "target_name": link_target,
                    })

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

            # 4. Create SHARES_TAG relationships
            tx.run(
                """
                MATCH (a:Note), (b:Note)
                WHERE a.path <> b.path
                WITH a, b, [tag IN a.tags WHERE tag IN b.tags] AS shared_tags
                UNWIND shared_tags AS tag
                MERGE (a)-[:SHARES_TAG {tag: tag}]->(b)
                """,
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
    vault_root = Path(vault_root or Config.VAULT_PATH).expanduser().resolve()
    own_collection = collection is None
    own_driver = neo4j_driver is None

    if own_collection:
        collection = create_collection(create_chroma_client())
    if own_driver:
        neo4j_driver = create_neo4j_driver()

    total_files = 0
    processed_files = 0
    note_records: list[NoteRecord] = []

    try:
        for file_path in discover_vault_files(vault_root):
            total_files += 1
            try:
                note_record = build_note_record(file_path, vault_root, strategy=strategy)
                if note_record is None:
                    logger.warning(f"Skipping empty file: {file_path.name}")
                    continue

                note_records.append(note_record)
                processed_files += 1
                logger.debug(f"Processed: {note_record['path']} ({len(note_record['chunks'])} chunks)")
            except Exception as exc:
                logger.error(f"Error processing {file_path}: {exc}")

        indexed_chunks = index_note_records(collection, note_records)
        sync_graph(neo4j_driver, note_records)

        return {
            "vault_root": str(vault_root),
            "total_files": total_files,
            "processed_files": processed_files,
            "indexed_chunks": indexed_chunks,
        }
    finally:
        if own_driver and neo4j_driver is not None:
            neo4j_driver.close()


def main() -> dict[str, Any]:
    setup_logging()
    logger.info(f"Starting indexing of files from {Config.VAULT_PATH}")
    summary = index_vault()
    logger.info(
        f"Indexing complete: {summary['processed_files']}/{summary['total_files']} files processed, "
        f"{summary['indexed_chunks']} chunks indexed"
    )
    return summary


if __name__ == "__main__":
    main()
