import ollama
import chromadb
from neo4j import GraphDatabase
from mcp.server.fastmcp import FastMCP
from pathlib import Path
from config import Config
from query_engine import BrainQueryEngine

# Initialize FastMCP Server
mcp = FastMCP("Clawdiney", port=8006, host="0.0.0.0")

# Singleton engine instance
engine = None

def get_engine():
    """Lazy initialization of engine with error handling"""
    global engine
    if engine is None:
        try:
            engine = BrainQueryEngine()
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
        return f"Brain Search Results for '{query}':\n\n{engine.query(query)}"
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