import ollama
import chromadb
from neo4j import GraphDatabase
from pathlib import Path
from config import Config

class BrainQueryEngine:
    def __init__(self):
        # ChromaDB Setup
        chroma_config = Config.get_chroma_client_config()
        if chroma_config["type"] == "http":
            self.chroma_client = chromadb.HttpClient(
                host=chroma_config["host"],
                port=chroma_config["port"]
            )
        else:
            self.chroma_client = chromadb.PersistentClient(path=chroma_config["path"])

        self.vector_collection = self.chroma_client.get_collection(name="obsidian_vault")

        # Neo4j Setup
        self.neo4j_driver = GraphDatabase.driver(
            Config.NEO4J_URI,
            auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
        )

    def close(self):
        self.neo4j_driver.close()

    def get_embedding(self, text):
        response = ollama.embeddings(model=MODEL_NAME, prompt=text)
        return response['embedding']

    def get_related_notes(self, note_name):
        """
        Fetches notes that are linked to the given note in Neo4j.
        """
        with self.neo4j_driver.session() as session:
            query = """
            MATCH (n:Note {name: $name})-[r:LINKS_TO]-(related:Note)
            RETURN related.name as name, related.path as path
            """
            result = session.run(query, name=note_name)
            return [record["name"] for record in result]

    def query(self, text, n_results=3, expand_graph=True):
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
        
        context_briefing = []
        seen_notes = set()

        for doc, meta in zip(docs, metadatas):
            filename = meta['filename']
            context_briefing.append(f"--- Source: {filename} ---\n{doc}")
            seen_notes.add(filename)

            # 2. Graph Expansion
            if expand_graph:
                related = self.get_related_notes(filename)
                for rel_note in related:
                    if rel_note not in seen_notes:
                        context_briefing.append(f"--- Related Note: {rel_note} (Linked via {filename}) ---")
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
