import pytest
from brain_indexer import OllamaEmbedding
from query_engine import BrainQueryEngine
from config import Config
import os
import shutil
import tempfile

@pytest.fixture(autouse=True)
def download_model():
    # Pre-download the model before any tests run
    embedding_function = OllamaEmbedding(model_name="bge-m3:latest")
    # Forçar download chamando a função com um texto de teste
    embedding_function(["test"])

@pytest.fixture
def temp_vault():
    # Cria um diretório temporário para o vault
    temp_dir = tempfile.mkdtemp()

    # Cria arquivos de teste
    with open(os.path.join(temp_dir, 'note1.md'), 'w') as f:
        f.write("# Design System\nThis is a note about design system. #design #ui")

    with open(os.path.join(temp_dir, 'note2.md'), 'w') as f:
        f.write("# Frontend Development\nThis is about frontend development. #frontend #design")

    with open(os.path.join(temp_dir, 'note3.md'), 'w') as f:
        f.write("# Backend Development\nThis is about backend development. #backend")

    # Configura a variável de ambiente para o vault temporário
    os.environ['VAULT_PATH'] = temp_dir
    Config.VAULT_PATH = temp_dir

    yield temp_dir

    # Limpa o diretório temporário
    shutil.rmtree(temp_dir)

def test_tag_indexing(temp_vault):
    engine = BrainQueryEngine()

    # Testa se as tags são indexadas corretamente
    results = engine.vector_collection.query(
        query_texts=["design"],
        n_results=3,
        where={"tags": {"$contains": "design"}}
    )

    assert len(results['documents'][0]) == 2
    assert "note1.md" in results['metadatas'][0][0]['filename']
    assert "note2.md" in results['metadatas'][0][1]['filename']

    # Testa se as tags estão presentes nos metadados
    for meta in results['metadatas'][0]:
        assert 'tags' in meta
        assert 'design' in meta['tags']

def test_tag_relationships(temp_vault):
    engine = BrainQueryEngine()

    # Testa se os relacionamentos por tags são criados corretamente
    related = engine.get_related_notes('note1.md')
    assert 'note2.md' in related

    related = engine.get_related_notes('note2.md')
    assert 'note1.md' in related
    assert 'note3.md' not in related

def test_reranking(temp_vault):
    engine = BrainQueryEngine()

    # Testa se o reranking está funcionando
    results = engine.query("design", n_results=2, use_rerank=True)

    # Verifica se os resultados estão ordenados corretamente
    assert "note1.md" in results
    assert "note2.md" in results

    # Verifica se o reranking está aplicando o threshold
    # (isso depende do modelo de reranking, então pode ser um teste simples)
    assert len(results.split('--- Source:')) == 2

def test_chunking_strategies(temp_vault):
    # Testa se o chunking está funcionando com diferentes estratégias
    # Configura a estratégia para headers
    os.environ['CHUNKING_STRATEGY'] = 'headers'

    # Reindexa o vault
    from brain_indexer import main
    main()

    # Verifica se os chunks foram criados corretamente
    engine = BrainQueryEngine()
    results = engine.vector_collection.query(query_texts=["design"], n_results=3)
    assert len(results['documents'][0]) > 0