# MCP Server via Docker

Este documento descreve como executar o Clawdiney MCP Server usando Docker.

## Pré-requisitos

1. Docker e Docker Compose instalados
2. Ollama rodando no host (para embeddings e rerank)
3. Um vault do Obsidian com arquivos `.md`

## Configuração

### 1. Criar arquivo `.env`

```bash
# Neo4j
NEO4J_USER=neo4j
NEO4J_PASSWORD=sua-senha-forte-aqui

# Vault
VAULT_PATH=/vault
VAULT_MOUNT_PATH=/caminho/para/seu/ObsidianVault

# Modelos (opcionais)
MODEL_NAME=bge-m3:latest
RERANK_MODEL_NAME=cross-encoder/ms-marco-MiniLM-L-6-v2
ENABLE_RERANK=true

# Ollama (apontar para o host)
OLLAMA_HOST=host.docker.internal
```

### 2. Configurar Ollama no Host

Para que o container acesse o Ollama rodando no host:

**Linux:**
```bash
# Ollama já escuta em 0.0.0.0 por padrão
sudo systemctl restart ollama
```

**Mac/Windows:**
```bash
# O Docker Desktop já resolve host.docker.internal automaticamente
```

## Executando

### Iniciar todos os serviços

```bash
docker compose up -d
```

Isso iniciará:
- **Neo4j** (porta 7474 browser, 7687 bolt)
- **ChromaDB** (porta 8000)
- **MCP Server** (porta 8006)

### Verificar status

```bash
docker compose ps
docker compose logs -f brain-mcp-server
```

### Parar serviços

```bash
docker compose down
```

## Integração com Claude Code

Adicione ao seu `~/.claude.json`:

```json
{
  "projects": {
    "/caminho/para/seu/projeto": {
      "mcpServers": {
        "clawdiney": {
          "command": "docker",
          "args": ["exec", "-i", "clawdiney-mcp-server", "python", "/app/mcp_wrapper.py"]
        }
      }
    }
  }
}
```

### Alternativa: Streamable HTTP

Para usar via HTTP (streamable-http):

```json
{
  "projects": {
    "/caminho/para/seu/projeto": {
      "mcpServers": {
        "clawdiney": {
          "url": "http://localhost:8006/mcp"
        }
      }
    }
  }
}
```

## Troubleshooting

### MCP Server não inicia

```bash
# Ver logs
docker compose logs brain-mcp-server

# Verificar se dependências estão up
docker compose ps neo4j chromadb
```

### Erro de conexão com Ollama

```bash
# Testar conexão do container
docker compose exec brain-mcp-server curl http://host.docker.internal:11434/api/tags

# Se falhar, verificar se Ollama está rodando
ollama list
```

### Erro de conexão com Neo4j/ChromaDB

Verifique se as redes Docker estão corretas:

```bash
docker network ls
docker network inspect clawdiney_brain-network
```

## Arquitetura

```
┌─────────────────┐     ┌──────────────────┐
│  Claude Code    │────▶│  MCP Server :8006│
└─────────────────┘     └────────┬─────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
       ┌────────────┐    ┌────────────┐    ┌────────────┐
       │  Neo4j     │    │  ChromaDB  │    │  Ollama    │
       │  :7687     │    │  :8000     │    │  :11434    │
       └────────────┘    └────────────┘    └────────────┘
```

## Scripts Úteis

```bash
# Reindexar o vault manualmente
docker compose exec brain-mcp-server python /app/brain_indexer.py

# Acessar shell do container
docker compose exec brain-mcp-server bash

# Ver volume do vault
docker compose exec brain-mcp-server ls -la /vault
```
