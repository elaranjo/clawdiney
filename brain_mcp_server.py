import ollama
import chromadb
from neo4j import GraphDatabase
from mcp.server.fastmcp import FastMCP
from pathlib import Path
from config import Config

# Initialize FastMCP Server
mcp = FastMCP("Clawdiney", port=8006, host="0.0.0.0")

# --- Internal Engine Setup ---
class BrainEngine:
    def __init__(self):
        # Initialize clients with error handling
        try:
            chroma_config = Config.get_chroma_client_config()
            self.chroma_client = chromadb.HttpClient(
                host=chroma_config["host"],
                port=chroma_config["port"]
            )
            self.vector_collection = self.chroma_client.get_collection(name="obsidian_vault")
        except Exception as e:
            raise Exception(f"Failed to initialize ChromaDB client: {str(e)}")

        try:
            self.neo4j_driver = GraphDatabase.driver(
                Config.NEO4J_URI,
                auth=(Config.NEO4J_USER, Config.NEO4J_PASSWORD)
            )
        except Exception as e:
            raise Exception(f"Failed to initialize Neo4j driver: {str(e)}")

    def __enter__(self):
        """Context manager entry"""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - automatically close connections"""
        self.close()

    def close(self):
        """Close all connections"""
        if hasattr(self, 'neo4j_driver'):
            self.neo4j_driver.close()

    def get_embedding(self, text):
        response = ollama.embeddings(model=Config.MODEL_NAME, prompt=text)
        return response['embedding']

    def get_related_notes(self, note_name):
        try:
            with self.neo4j_driver.session() as session:
                query = "MATCH (n:Note {name: $name})-[r:LINKS_TO]-(related:Note) RETURN related.name as name"
                result = session.run(query, name=note_name)
                return [record["name"] for record in result]
        except Exception as e:
            print(f"Error getting related notes: {str(e)}")
            return []

    def search(self, query_text, n_results=3):
        try:
            embedding = self.get_embedding(query_text)
            results = self.vector_collection.query(query_embeddings=[embedding], n_results=n_results)

            docs = results['documents'][0]
            metadatas = results['metadatas'][0]

            briefing = []
            for doc, meta in zip(docs, metadatas):
                briefing.append(f"Source: {meta['filename']}\nContent: {doc}")
            return "\n\n".join(briefing)
        except Exception as e:
            return f"Error during search: {str(e)}"

    def read_note(self, filename):
        """Read a note from the vault with intelligent path resolution"""
        try:
            vault_path = Path(Config.VAULT_PATH)
            # Find all matching files
            matching_files = list(vault_path.rglob(filename))

            if not matching_files:
                return f"Error: Note {filename} not found in Vault."
            elif len(matching_files) > 1:
                # If multiple files found, return all candidates
                paths_list = "\n".join([f"- {str(f.relative_to(vault_path))}" for f in matching_files])
                return f"Multiple files found for '{filename}' ({len(matching_files)} matches):\n{paths_list}\n\nPlease specify which file you want to read."
            else:
                # Single file found
                return matching_files[0].read_text(encoding='utf-8')
        except Exception as e:
            return f"Error reading note {filename}: {str(e)}"

# Singleton engine instance
engine = None

def get_engine():
    """Lazy initialization of engine with error handling"""
    global engine
    if engine is None:
        try:
            engine = BrainEngine()
        except Exception as e:
            raise Exception(f"Failed to initialize BrainEngine: {str(e)}")
    return engine

# --- MCP Tools ---

@mcp.tool()
def search_brain(query: str) -> str:
    """
    Search Clawdiney for architectural patterns, SOPs, and design system components.
    Use this whenever you need to verify a standard or find existing implementation patterns.
    """
    try:
        engine = get_engine()
        return f"Brain Search Results for '{query}':\n\n{engine.search(query)}"
    except Exception as e:
        return f"Error in search_brain: {str(e)}"

@mcp.tool()
def explore_graph(note_name: str) -> str:
    """
    Explore the knowledge graph to find notes related to a specific topic.
    Returns a list of connected notes based on [[WikiLinks]].
    """
    try:
        engine = get_engine()
        related = engine.get_related_notes(note_name)
        if not related:
            return f"No direct connections found for note: {note_name}"
        return f"Notes connected to {note_name}:\n" + "\n".join([f"- {r}" for r in related])
    except Exception as e:
        return f"Error in explore_graph: {str(e)}"

@mcp.tool()
def read_full_note(filename: str) -> str:
    """
    Read the entire content of a specific note from the Vault.
    Use this when you have found a relevant note and need the full detailed specification.
    """
    try:
        engine = get_engine()
        return engine.read_note(filename)
    except Exception as e:
        return f"Error in read_full_note: {str(e)}"

if __name__ == "__main__":
    try:
        mcp.run()
    finally:
        # Clean up resources
        if engine is not None:
            engine.close()