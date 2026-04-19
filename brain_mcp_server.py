import os
import ollama
import chromadb
from neo4j import GraphDatabase
from mcp.server.fastmcp import FastMCP
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Configuration from .env ---
VAULT_PATH = os.path.expanduser(os.getenv("VAULT_PATH", "~/Documents/ObsidianVault"))
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
MODEL_NAME = os.getenv("MODEL_NAME", "bge-m3")

NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

# Initialize FastMCP Server
mcp = FastMCP("Clawdiney", port=8006, host="0.0.0.0")

# --- Internal Engine Setup ---
class BrainEngine:
    def __init__(self):
        self.chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        self.vector_collection = self.chroma_client.get_collection(name="obsidian_vault")
        self.neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    def get_embedding(self, text):
        response = ollama.embeddings(model=MODEL_NAME, prompt=text)
        return response['embedding']

    def get_related_notes(self, note_name):
        with self.neo4j_driver.session() as session:
            query = "MATCH (n:Note {name: $name})-[r:LINKS_TO]-(related:Note) RETURN related.name as name"
            result = session.run(query, name=note_name)
            return [record["name"] for record in result]

    def search(self, query_text, n_results=3):
        embedding = self.get_embedding(query_text)
        results = self.vector_collection.query(query_embeddings=[embedding], n_results=n_results)
        
        docs = results['documents'][0]
        metadatas = results['metadatas'][0]
        
        briefing = []
        for doc, meta in zip(docs, metadatas):
            briefing.append(f"Source: {meta['filename']}\nContent: {doc}")
        return "\n\n".join(briefing)

    def read_note(self, filename):
        # Find the path in the vault
        path = Path(VAULT_PATH).rglob(filename)
        try:
            file_path = next(path)
            return file_path.read_text(encoding='utf-8')
        except StopIteration:
            return f"Error: Note {filename} not found in Vault."

# Singleton engine instance
engine = BrainEngine()

# --- MCP Tools ---

@mcp.tool()
def search_brain(query: str) -> str:
    """
    Search Clawdiney for architectural patterns, SOPs, and design system components.
    Use this whenever you need to verify a standard or find existing implementation patterns.
    """
    return f"Brain Search Results for '{query}':\n\n{engine.search(query)}"

@mcp.tool()
def explore_graph(note_name: str) -> str:
    """
    Explore the knowledge graph to find notes related to a specific topic.
    Returns a list of connected notes based on [[WikiLinks]].
    """
    related = engine.get_related_notes(note_name)
    if not related:
        return f"No direct connections found for note: {note_name}"
    return f"Notes connected to {note_name}:\n" + "\n".join([f"- {r}" for r in related])

@mcp.tool()
def read_full_note(filename: str) -> str:
    """
    Read the entire content of a specific note from the Vault.
    Use this when you have found a relevant note and need the full detailed specification.
    """
    return engine.read_note(filename)

if __name__ == "__main__":
    mcp.run()