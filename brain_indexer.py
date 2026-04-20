import os
import ollama
import chromadb
from neo4j import GraphDatabase
from pathlib import Path
from config import Config
from chromadb.utils.embedding_functions import EmbeddingFunction

# Configurações do ChromaDB via HTTP usando Config
CHROMA_HOST = Config.CHROMA_HOST
CHROMA_PORT = Config.CHROMA_PORT
client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)

# Configurações do Neo4j usando Config
NEO4J_URI = Config.NEO4J_URI
NEO4J_USER = Config.NEO4J_USER
NEO4J_PASSWORD = Config.NEO4J_PASSWORD

# Caminho do Vault usando Config
VAULT_PATH = Config.VAULT_PATH

# Modelo de embedding usando Config
MODEL_NAME = Config.MODEL_NAME

# Inicializa o Neo4j
neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

# Classe de embedding customizada
class OllamaEmbedding(EmbeddingFunction):
    def __init__(self, model_name="bge-m3:latest"):
        self.model_name = model_name
        self.ollama_client = ollama.Client(timeout=600)

    def __call__(self, input: list[str]) -> list[list[float]]:
        embeddings = []
        for text in input:
            response = self.ollama_client.embeddings(model=self.model_name, prompt=text)
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

# Prepara lista para armazenar dados dos arquivos para Neo4j
vault_files = []

def fixed_size_chunking(text, chunk_size=500, overlap=50):
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]
        chunks.append(chunk)
        start = end - overlap
    return [{"header": "Fixed Size", "content": chunk} for chunk in chunks]

def semantic_chunking(text):
    import re
    # Split by sentence endings
    sentences = re.split(r'(?<=[.!?]) +', text)
    chunks = []
    current_chunk = ""
    for sentence in sentences:
        if len(current_chunk) + len(sentence) > Config.CHUNK_SIZE:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = sentence
            else:
                current_chunk = sentence
        else:
            current_chunk += sentence + " "
    if current_chunk:
        chunks.append(current_chunk)
    return [{"header": "Semantic", "content": chunk} for chunk in chunks]

def markdown_chunking(text):
    """
    Smarter chunking that respects Markdown headers.
    Splits by H1, H2, H3 to keep sections together.
    """
    import re
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

def chunk_text(text):
    strategy = Config.CHUNKING_STRATEGY
    if strategy == "headers":
        return markdown_chunking(text)
    elif strategy == "fixed":
        return fixed_size_chunking(text, Config.CHUNK_SIZE, Config.CHUNK_OVERLAP)
    elif strategy == "semantic":
        return semantic_chunking(text)
    else:
        # default to headers
        return markdown_chunking(text)

# Processa todos os arquivos .md no Vault com chunking
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

        # Extrai tags do arquivo (formato #tag)
        import re
        tags = re.findall(r'#(\w+)', content)
        vault_files.append({
            "name": file_path.name,
            "content": content,
            "tags": tags
        })

        # Aplica chunking com estratégia configurável
        chunks = chunk_text(content)

        # Adiciona cada chunk como documento separado
        for i, chunk in enumerate(chunks):
            chunk_content = f"File: {file_path.name}\nSection: {chunk['header']}\n\n{chunk['content']}"
            collection.add(
                documents=[chunk_content],
                metadatas=[{
                    "filename": file_path.name,
                    "header": chunk['header'],
                    "source": str(file_path)
                }],
                ids=[f"{file_path}_{i}"]
            )
        processed += 1
        print(f"✅ Processed: {file_path.name} ({len(chunks)} chunks)")
    except Exception as e:
        print(f"❌ Error processing {file_path}: {e}")

# Atualiza o grafo no Neo4j usando MERGE/UPSERT
with neo4j_driver.session() as session:
    # Primeiro, atualizamos ou criamos nós para cada arquivo com conteúdo
    session.run("""
    UNWIND $files AS file
    MERGE (n:Note {name: file.name})
    SET n.content = file.content,
        n.last_indexed = timestamp(),
        n.tags = file.tags
    """, files=vault_files)

    # Em seguida, atualizamos os relacionamentos usando MERGE
    # Primeiro limpamos relacionamentos existentes (mas mantemos os nós)
    session.run("MATCH ()-[r:LINKS_TO]->() DELETE r")

    # Depois criamos novos relacionamentos baseado em WikiLinks do Obsidian [[nome]]
    session.run("""
    MATCH (a:Note), (b:Note)
    WHERE a.name <> b.name AND EXISTS {
        MATCH (doc:Note {name: a.name})
        WHERE doc.content CONTAINS '[[' + b.name + ']]'
    }
    MERGE (a)-[:LINKS_TO]->(b)
    """)

    # Criar relacionamentos baseados em tags compartilhadas
    session.run("""
    MATCH (a:Note), (b:Note)
    WHERE a <> b
    WITH a, b, [tag IN a.tags WHERE tag IN b.tags] AS sharedTags
    UNWIND sharedTags AS tag
    MERGE (a)-[:SHARES_TAG {tag: tag}]->(b)
    """)

    print("✅ Neo4j graph updated successfully!")

print(f"✅ Brain Indexing Complete! ({processed}/{total_files} files processed)")

# Testa a coleção
results = collection.query(query_texts=["test"], n_results=1)
print("🔍 Test query results:", results)