import os
import ollama
import chromadb
from neo4j import GraphDatabase
from pathlib import Path
from dotenv import load_dotenv
from chromadb.utils.embedding_functions import EmbeddingFunction

# Carrega variáveis de ambiente
load_dotenv()

# Configurações do ChromaDB via HTTP
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)

# Configurações do Neo4j
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password123")

# Caminho do Vault
VAULT_PATH = os.path.expanduser(os.getenv("VAULT_PATH", "~/Documents/ObsidianVault"))

# Modelo de embedding
MODEL_NAME = os.getenv("MODEL_NAME", "bge-m3:latest")

# Inicializa o Neo4j
neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# Classe de embedding customizada
class OllamaEmbedding(EmbeddingFunction):
    def __init__(self, model_name="bge-m3:latest"):
        self.model_name = model_name
    
    def __call__(self, input: list[str]) -> list[list[float]]:
        embeddings = []
        for text in input:
            response = ollama.embeddings(model=self.model_name, prompt=text)
            embeddings.append(response["embedding"])
        return embeddings
    
    def name(self) -> str:
        return f"ollama_{self.model_name}"

# Cria a coleção com a função de embedding correta
embedding_function = OllamaEmbedding(model_name=MODEL_NAME)
collection = client.get_or_create_collection(
    name="obsidian_vault",
    embedding_function=embedding_function
)

print("🚀 Starting Indexing of files from", VAULT_PATH)

# Processa todos os arquivos .md no Vault
total_files = 0
processed = 0
for file_path in Path(VAULT_PATH).rglob("*.md"):
    total_files += 1
    try:
        content = file_path.read_text(encoding='utf-8')
        # Ignora arquivos vazios
        if not content.strip():
            print(f"⚠️ Skipping empty file: {file_path.name}")
            continue
        
        # Adiciona diretamente
        collection.add(
            documents=[content],
            metadatas=[{"filename": file_path.name}],
            ids=[str(file_path)]
        )
        processed += 1
        print(f"✅ Processed: {file_path.name}")
    except Exception as e:
        print(f"❌ Error processing {file_path}: {e}")

# Atualiza o grafo no Neo4j
with neo4j_driver.session() as session:
    session.run("MATCH (n) DETACH DELETE n")  # Limpa o grafo existente
    # Cria nós para cada arquivo
    session.run("UNWIND $files AS file CREATE (:Note {name: file})",
                files=[f.name for f in Path(VAULT_PATH).rglob("*.md")])
    # Cria links entre notas (exemplo simplificado)
    session.run("""
    MATCH (a:Note), (b:Note)
    WHERE a.name <> b.name AND a.name CONTAINS '[[ ' + b.name + ' ]]'
    CREATE (a)-[:LINKS_TO]->(b)
    """)

print(f"✅ Brain Indexing Complete! ({processed}/{total_files} files processed)")

# Testa a coleção
results = collection.query(query_texts=["test"], n_results=1)
print("🔍 Test query results:", results)