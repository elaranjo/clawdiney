from pathlib import Path
import re

import chromadb
import ollama
from chromadb.utils.embedding_functions import EmbeddingFunction
from neo4j import GraphDatabase

from config import Config


class OllamaEmbedding(EmbeddingFunction):
    def __init__(self, model_name=None):
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


def create_chroma_client():
    return chromadb.HttpClient(host=Config.CHROMA_HOST, port=Config.CHROMA_PORT)


def create_collection(client):
    return client.get_or_create_collection(
        name="obsidian_vault",
        embedding_function=OllamaEmbedding(model_name=Config.MODEL_NAME),
    )


def create_neo4j_driver():
    return GraphDatabase.driver(
        Config.NEO4J_URI,
        auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD),
    )


def extract_tags(content):
    return sorted(set(re.findall(r"(?<!\w)#([A-Za-z0-9_/-]+)", content)))


def fixed_size_chunking(text, chunk_size=500, overlap=50):
    chunks = []
    start = 0

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append({"header": "Fixed Size", "content": chunk.strip()})
        start = end - overlap if overlap < chunk_size else end

    return [chunk for chunk in chunks if chunk["content"]]


def semantic_chunking(text, chunk_size=None):
    sentences = re.split(r"(?<=[.!?])\s+", text)
    chunks = []
    current_chunk = ""
    target_size = chunk_size or Config.CHUNK_SIZE

    for sentence in sentences:
        if len(current_chunk) + len(sentence) > target_size and current_chunk:
            chunks.append({"header": "Semantic", "content": current_chunk.strip()})
            current_chunk = sentence
        else:
            current_chunk = f"{current_chunk} {sentence}".strip()

    if current_chunk:
        chunks.append({"header": "Semantic", "content": current_chunk.strip()})

    return chunks


def markdown_chunking(text):
    chunks = []
    current_header = "Root"
    current_lines = []

    for line in text.splitlines():
        if re.match(r"^#+\s", line):
            if current_lines:
                chunks.append({
                    "header": current_header,
                    "content": "\n".join(current_lines).strip(),
                })
            current_header = line.lstrip("#").strip() or "Root"
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        chunks.append({
            "header": current_header,
            "content": "\n".join(current_lines).strip(),
        })

    if not chunks and text.strip():
        chunks.append({"header": "Root", "content": text.strip()})

    return [chunk for chunk in chunks if chunk["content"] or chunk["header"] != "Root"]


def chunk_text(text, strategy=None, chunk_size=None, overlap=None):
    strategy = strategy or Config.CHUNKING_STRATEGY
    chunk_size = chunk_size or Config.CHUNK_SIZE
    overlap = overlap if overlap is not None else Config.CHUNK_OVERLAP

    if strategy == "headers":
        return markdown_chunking(text)
    if strategy == "fixed":
        return fixed_size_chunking(text, chunk_size, overlap)
    if strategy == "semantic":
        return semantic_chunking(text, chunk_size)
    return markdown_chunking(text)


def discover_vault_files(vault_root):
    return sorted(vault_root.rglob("*.md"))


def build_note_record(file_path, vault_root, strategy=None):
    content = file_path.read_text(encoding="utf-8")
    if not content.strip():
        return None

    relative_path = file_path.relative_to(vault_root).as_posix()
    tags = extract_tags(content)
    chunks = chunk_text(content, strategy=strategy)

    return {
        "name": file_path.name,
        "path": relative_path,
        "source": str(file_path),
        "content": content,
        "tags": tags,
        "chunks": chunks,
    }


def build_chunk_payload(note_record):
    ids = []
    documents = []
    metadatas = []

    for index, chunk in enumerate(note_record["chunks"]):
        metadata = {
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


def index_note_records(collection, note_records):
    indexed_chunks = 0

    for note_record in note_records:
        ids, documents, metadatas = build_chunk_payload(note_record)
        if not ids:
            continue
        collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
        indexed_chunks += len(ids)

    return indexed_chunks


def sync_graph(neo4j_driver, note_records):
    with neo4j_driver.session() as session:
        session.run(
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

        session.run("MATCH ()-[r:LINKS_TO|SHARES_TAG]->() DELETE r")

        session.run(
            """
            MATCH (a:Note), (b:Note)
            WHERE a.path <> b.path
              AND (
                a.content CONTAINS '[[' + b.path + ']]'
                OR a.content CONTAINS '[[' + b.name + ']]'
              )
            MERGE (a)-[:LINKS_TO]->(b)
            """
        )

        session.run(
            """
            MATCH (a:Note), (b:Note)
            WHERE a.path <> b.path
            WITH a, b, [tag IN a.tags WHERE tag IN b.tags] AS shared_tags
            UNWIND shared_tags AS tag
            MERGE (a)-[:SHARES_TAG {tag: tag}]->(b)
            """
        )


def index_vault(vault_root=None, collection=None, neo4j_driver=None, strategy=None):
    vault_root = Path(vault_root or Config.VAULT_PATH).expanduser().resolve()
    own_collection = collection is None
    own_driver = neo4j_driver is None

    if own_collection:
        collection = create_collection(create_chroma_client())
    if own_driver:
        neo4j_driver = create_neo4j_driver()

    total_files = 0
    processed_files = 0
    note_records = []

    try:
        for file_path in discover_vault_files(vault_root):
            total_files += 1
            try:
                note_record = build_note_record(file_path, vault_root, strategy=strategy)
                if note_record is None:
                    print(f"⚠️ Skipping empty file: {file_path.name}")
                    continue

                note_records.append(note_record)
                processed_files += 1
                print(f"✅ Processed: {note_record['path']} ({len(note_record['chunks'])} chunks)")
            except Exception as exc:
                print(f"❌ Error processing {file_path}: {exc}")

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


def main():
    print(f"🚀 Starting Indexing of files from {Config.VAULT_PATH}")
    summary = index_vault()
    print(
        f"✅ Brain Indexing Complete! "
        f"({summary['processed_files']}/{summary['total_files']} files processed, "
        f"{summary['indexed_chunks']} chunks indexed)"
    )
    return summary


if __name__ == "__main__":
    main()
