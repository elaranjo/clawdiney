from pathlib import Path
import re

import chromadb
import ollama
from neo4j import GraphDatabase

from config import Config

class BrainQueryEngine:
    def __init__(self):
        self.vault_root = Path(Config.VAULT_PATH).expanduser().resolve()

        # ChromaDB Setup - Always use HTTP client
        chroma_config = Config.get_chroma_client_config()
        self.chroma_client = chromadb.HttpClient(
            host=chroma_config["host"],
            port=chroma_config["port"]
        )
        # Configura timeout para 60 segundos no cliente httpx subjacente
        import httpx
        self.chroma_client.timeout = httpx.Timeout(300.0)
        self.vector_collection = self.chroma_client.get_collection(name="obsidian_vault")

        # Neo4j Setup
        self.neo4j_driver = GraphDatabase.driver(
            Config.NEO4J_URI,
            auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
        )

    def close(self):
        self.neo4j_driver.close()

    def get_embedding(self, text):
        response = ollama.embeddings(model=Config.MODEL_NAME, prompt=text)
        return response['embedding']

    def _normalize_note_path(self, note_path):
        """Return a canonical vault-relative path and ensure it stays inside the vault."""
        raw_path = Path(note_path).expanduser()
        if raw_path.is_absolute():
            resolved = raw_path.resolve()
        else:
            resolved = (self.vault_root / raw_path).resolve()

        try:
            return resolved.relative_to(self.vault_root).as_posix()
        except ValueError as exc:
            raise ValueError(f"Path '{note_path}' is outside the configured vault") from exc

    def _resolve_note_path(self, note_path):
        relative_path = self._normalize_note_path(note_path)
        absolute_path = self.vault_root / relative_path
        if not absolute_path.is_file():
            raise FileNotFoundError(f"Note not found: {relative_path}")
        return absolute_path, relative_path

    def _split_note_into_chunks(self, content):
        """Split markdown text by headers for local note inspection."""
        chunks = []
        current_header = "Root"
        current_lines = []

        for line in content.splitlines():
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

        if not chunks and content.strip():
            chunks.append({
                "header": "Root",
                "content": content.strip(),
            })

        return chunks

    def resolve_note(self, name):
        """Return candidate notes that match a basename or relative path fragment."""
        query = name.strip().lower()
        if not query:
            return []

        candidates = []
        for file_path in self.vault_root.rglob("*.md"):
            relative_path = file_path.relative_to(self.vault_root).as_posix()
            filename = file_path.name
            filename_lower = filename.lower()
            relative_lower = relative_path.lower()

            score = None
            if filename_lower == query or relative_lower == query:
                score = 0
            elif relative_lower.endswith(f"/{query}"):
                score = 1
            elif filename_lower.startswith(query):
                score = 2
            elif query in filename_lower:
                score = 3
            elif query in relative_lower:
                score = 4

            if score is None:
                continue

            candidates.append({
                "path": relative_path,
                "filename": filename,
                "score": score,
            })

        candidates.sort(key=lambda item: (item["score"], item["path"]))
        return candidates

    def get_note_by_path(self, path):
        absolute_path, relative_path = self._resolve_note_path(path)
        return {
            "path": relative_path,
            "filename": absolute_path.name,
            "content": absolute_path.read_text(encoding="utf-8"),
        }

    def read_source(self, source_path):
        return self.get_note_by_path(source_path)["content"]

    def get_note_chunks(self, filename):
        candidates = self.resolve_note(filename)
        if not candidates:
            raise FileNotFoundError(f"No notes found for '{filename}'")
        if len(candidates) > 1 and candidates[0]["path"] != filename:
            candidate_paths = ", ".join(candidate["path"] for candidate in candidates[:10])
            raise ValueError(
                f"Multiple notes match '{filename}'. Resolve a canonical path first: {candidate_paths}"
            )

        note = self.get_note_by_path(candidates[0]["path"])
        chunks = self._split_note_into_chunks(note["content"])
        return [
            {
                "path": note["path"],
                "filename": note["filename"],
                "header": chunk["header"],
                "content": chunk["content"],
                "chunk_index": index,
            }
            for index, chunk in enumerate(chunks)
        ]

    def get_related_notes(self, note_ref):
        """
        Fetches notes that are linked to the given note in Neo4j, including tag-based relationships.
        """
        with self.neo4j_driver.session() as session:
            query = """
            MATCH (n:Note)-[:LINKS_TO|SHARES_TAG]-(related:Note)
            WHERE n.path = $note_ref OR n.name = $note_ref
            RETURN related.name as name, related.path as path
            """
            result = session.run(query, note_ref=note_ref)
            return [record["path"] or record["name"] for record in result]

    def rerank_results(self, query, results):
        """Rerank results using cross-encoder model"""
        scored_results = []
        successful_scores = 0
        for doc, meta in results:
            combined = f"Output only the relevance score between 0 and 1. Query: {query}\nDocument: {doc}"
            try:
                response = ollama.generate(
                    model=Config.RERANK_MODEL_NAME,
                    prompt=combined,
                    options={"temperature": 0}
                )
                # Extract score from response
                score_str = response.get('response', '').strip()
                try:
                    score = float(score_str)
                    successful_scores += 1
                except:
                    score = None
            except Exception:
                score = None
            scored_results.append((score, doc, meta))

        if successful_scores == 0:
            return results

        threshold = float(Config.RERANK_THRESHOLD)
        filtered_results = [item for item in scored_results if item[0] is not None and item[0] >= threshold]

        if not filtered_results:
            return results

        filtered_results.sort(key=lambda x: x[0], reverse=True)
        return [(doc, meta) for score, doc, meta in filtered_results]

    def query(self, text, n_results=3, expand_graph=True, use_rerank=True):
        """
        Hybrid Semantic + Graph search.
        """
        # 1. Semantic Search
        embedding = self.get_embedding(text)
        results = self.vector_collection.query(
            query_embeddings=[embedding],
            n_results=n_results
        )

        docs = results['documents'][0]
        metadatas = results['metadatas'][0]

        # 2. Rerank results if enabled
        if use_rerank and Config.ENABLE_RERANK and docs:
            reranked = self.rerank_results(text, list(zip(docs, metadatas)))
            if reranked:
                docs, metadatas = zip(*reranked)
                # Limit to n_results
                docs = docs[:n_results]
                metadatas = metadatas[:n_results]

        context_briefing = []
        seen_notes = set()

        for doc, meta in zip(docs, metadatas):
            note_identifier = meta.get('path') or meta['filename']
            note_label = meta.get('path') or meta['filename']
            context_briefing.append(f"--- Source: {note_label} ---\n{doc}")
            seen_notes.add(note_identifier)

            # 3. Graph Expansion
            if expand_graph:
                related = self.get_related_notes(note_identifier)
                for rel_note in related:
                    if rel_note not in seen_notes:
                        context_briefing.append(
                            f"--- Related Note: {rel_note} (Linked via {note_label}) ---"
                        )
                        seen_notes.add(rel_note)

        return "\n\n".join(context_briefing)

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print("Usage: python brain_query_engine.py 'your search query'")
        sys.exit(1)

    query_text = " ".join(sys.argv[1:])
    engine = BrainQueryEngine()
    try:
        briefing = engine.query(query_text)
        print(f"\n=== BRAIN CONTEXT BRIEFING ===\n\n{briefing}\n\n==============================")
    finally:
        engine.close()
