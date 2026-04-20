import re
import ollama
import chromadb
from chromadb.utils import embedding_functions
from tqdm import tqdm
from pathlib import Path
from config import Config

class ObsidianIndexer:
    def __init__(self):
        # Always use HTTP client for ChromaDB
        chroma_config = Config.get_chroma_client_config()
        self.client = chromadb.HttpClient(
            host=chroma_config["host"],
            port=chroma_config["port"]
        )

        # We use a custom embedding function that calls Ollama
        self.collection = self.client.get_or_create_collection(
            name="obsidian_vault",
            metadata={"hnsw:space-type": "cosine"}
        )

    def get_embedding(self, text):
        response = ollama.embeddings(model=Config.MODEL_NAME, prompt=text)
        return response['embedding']

    def markdown_chunking(self, text):
        """
        Smarter chunking that respects Markdown headers.
        Splits by H1, H2, H3 to keep sections together.
        """
        # Split by headers: #, ##, ###
        sections = re.split(r'(^#+\s.*$)', text, flags=re.MULTILINE)
        
        chunks = []
        current_section = ""
        current_header = "Root"

        for part in sections:
            if part.startswith('#'):
                if current_section:
                    chunks.append({"header": current_header, "content": current_section.strip()})
                current_header = part.replace('#', '').strip()
                current_section = ""
            else:
                current_section += part + "\n"
        
        if current_section:
            chunks.append({"header": current_header, "content": current_section.strip()})
        
        return chunks

    def index_vault(self):
        vault_path = Path(Config.VAULT_PATH)
        vault_files = list(vault_path.rglob("*.md"))
        print(f"Indexing {len(vault_files)} files from {Config.VAULT_PATH}...")

        for file_path in tqdm(vault_files):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                chunks = self.markdown_chunking(content)
                
                for i, chunk in enumerate(chunks):
                    text = f"File: {file_path.name}\nSection: {chunk['header']}\n\n{chunk['content']}"
                    embedding = self.get_embedding(text)
                    
                    self.collection.add(
                        ids=[f"{file_path.name}_{i}"],
                        embeddings=[embedding],
                        metadatas=[{
                            "source": str(file_path),
                            "filename": file_path.name,
                            "header": chunk['header']
                        }],
                        documents=[text]
                    )
            except Exception as e:
                print(f"Error indexing {file_path}: {e}")

if __name__ == "__main__":
    indexer = ObsidianIndexer()
    indexer.index_vault()
    print("Indexing complete!")
