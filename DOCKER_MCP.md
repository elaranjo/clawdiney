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

> Nota: `OLLAMA_HOST=host.docker.internal` é obrigatório para que o container Docker alcance o Ollama rodando no host.

## Executando

### Iniciar todos os serviços

```bash
docker compose up -d
```

Isso iniciará:
- **Neo4j** (porta 7476 browser, 7689 bolt — portas externas mapeadas para 7474/7687 internas)
- **ChromaDB** (porta 8001)
- **MCP Server** (porta 8006)

### Verificar status

```bash
docker compose ps
docker compose logs -f clawdiney-mcp-server
```

### Parar serviços

```bash
docker compose down
```

## Integração com Claude Code

O MCP server usa SSE (Server-Sent Events) na porta 8006.

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
docker compose logs clawdiney-mcp-server

# Verificar se dependências estão up
docker compose ps neo4j chromadb
```

### Erro de conexão com Ollama

```bash
# Se falhar, verificar se Ollama está rodando
ollama list
```

### Container em loop de restart

Se o container `clawdiney-mcp-server` estiver reiniciando repetidamente:

```bash
# Ver logs para diagnóstico
docker compose -f docker/docker-compose.yml logs mcp-server

# Verificar status do container
docker compose -f docker/docker-compose.yml ps mcp-server
```

Causa: O transporte `stdio` não é compatível com containers Docker em modo detached (o stdin fechado causa EOF, que encerra o processo).

Solução: O container foi configurado para usar transporte `sse` (porta 8006). Certifique-se de que:
- `MCP_TRANSPORT=sse` está definido no `docker-compose.yml`
- `OLLAMA_HOST=host.docker.internal` está definido (necessário para embeddings)

### Erro de conexão com Neo4j/ChromaDB

Verifique se as redes Docker estão corretas:

```bash
docker network ls
docker network inspect docker_brain-network
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
docker compose exec clawdiney-mcp-server python -m clawdiney.indexer

# Acessar shell do container
docker compose exec clawdiney-mcp-server bash

# Ver volume do vault
docker compose exec clawdiney-mcp-server ls -la /vault
```
