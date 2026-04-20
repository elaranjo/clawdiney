# 🧠 Clawdiney

**Cérebro Expandido para Agentes de Codificação**

Um sistema híbrido de **Vetores + Grafo** que transforma seu Obsidian Vault em uma fonte de conhecimento viva para o Claude Code.

---

## 🚀 Visão Geral

O Clawdiney permite que agentes de IA (como o Claude Code) consultem sua base de conhecimento de forma inteligente:

- **Busca Semântica:** Encontra padrões, SOPs e componentes por significado (não apenas palavras-chave).
- **Grafo de Conhecimento:** Mapeia relações entre notas via `[[WikiLinks]]`.
- **Integração Nativa:** Conecta-se ao Claude Code via MCP (Model Context Protocol).

---

## 📋 Pré-requisitos

Antes de começar, certifique-se de ter instalado:

| Software | Versão Mínima | Link |
|----------|---------------|------|
| **Docker** | 20.x+ | [docker.com](https://docs.docker.com/get-docker/) |
| **Docker Compose** | 2.x+ | Incluído no Docker Desktop ou `apt install docker-compose-plugin` |
| **Ollama** | 0.1.x+ | [ollama.com](https://ollama.com/) |
| **Python** | 3.10+ | Geralmente já instalado em sistemas Unix. Se não: `apt install python3` ou `brew install python@3.12` |
| **Claude Code** | Latest | `ollama launch claude` |

**Sistemas Suportados:**
- ✅ Linux (Ubuntu, Debian, Fedora, Arch, etc.)
- ✅ macOS (Intel e Apple Silicon)
- ✅ WSL2 (Windows Subsystem for Linux)
- ✅ BSD (FreeBSD, OpenBSD - com ajustes manuais)

---

## 🛠️ Instalação Rápida

Existem **três formas** de instalar o Clawdiney:

---

### Opção 0: Criar o Vault do Zero (Se não tiver um)

Se você **ainda não tem um vault** da firma, use o script de criação:

```bash
chmod +x setup_vault.sh
./setup_vault.sh
```

**O script vai:**
- ✅ Criar estrutura de pastas (P.A.R.A. method)
- ✅ Criar `00_Index.md` (documentação do vault)
- ✅ Criar SOPs básicos (Backend, Design System, etc.)
- ✅ Criar `Agent_Protocol.md` (instruções para IA)
- ✅ Opcional: Inicializar repositório Git

**Tempo estimado:** 1-2 minutos

---

### Opção 1: Via Arquivo Compactado (Mais Rápido)

**1. Baixe o arquivo** `clawdiney-kit-v1.tar.gz`

**2. Extraia na pasta de projetos:**
```bash
tar -xzvf clawdiney-kit-v1.tar.gz -C ~/projetos/
cd ~/projetos/clawdiney
```

> **Nota:** Se preferir outra pasta, ajuste conforme necessário. Apenas mantenha a estrutura organizada.

**3. Configure o `.env`:**
```bash
cp .env.example .env
nano .env  # Ou use seu editor preferido (vim, code, etc.)
```

**Edite a linha do `VAULT_PATH`** para apontar para o seu Obsidian Vault da firma:
```bash
VAULT_PATH=~/Documents/CompanyVault
```

**4. Execute o Bootstrapper:**
```bash
chmod +x setup_brain.sh
./setup_brain.sh
```

---

### Opção 2: Via Git (Recomendado para Times)

**1. Clone o repositório do Vault da Firma** (se ainda não tiver):
```bash
git clone git@github.com:[SUA_FIRMA]/company-vault.git ~/Documents/CompanyVault
```

> **Dica:** Em sistemas Linux, você pode usar `~/documentos/` ou qualquer pasta de sua preferência. Apenas seja consistente.

**2. Clone este repositório:**
```bash
git clone git@github.com:[SUA_FIRMA]/clawdiney.git ~/projetos/clawdiney
cd ~/projetos/clawdiney
```

**3. Configure o `.env`:**
```bash
cp .env.example .env
nano .env
```

**4. Execute o Bootstrapper:**
```bash
chmod +x setup_brain.sh
./setup_brain.sh
```

---

## 📋 O Que o Bootstrapper Faz

O script `setup_brain.sh` executa automaticamente:

| Passo | Ação |
|-------|------|
| 🔍 | Verifica se Docker, Docker Compose e Ollama estão instalados |
| 📝 | Cria o `.env` com configurações padrão (se não existir) |
| 🐳 | Sobe containers Neo4j + ChromaDB via Docker Compose |
| 🐍 | Cria ambiente virtual Python (`venv`) |
| 📦 | Instala dependências Python (`neo4j`, `chromadb`, `ollama`, etc.) |
| ✅ | **Verifica e auto-repara** dependências faltantes |
| 🦙 | Baixa o modelo de embeddings (`bge-m3`) via Ollama |
| 🧠 | Indexa seu Vault no banco de dados |

**Tempo estimado:** 3-5 minutos (dependendo do tamanho do Vault e velocidade da internet)

---

## ⚙️ Configuração Manual (Opcional)

### 1. Editar o `.env`

Após rodar o bootstrapper (ou manualmente), edite o arquivo `.env`:

```bash
# Caminho para o seu Obsidian Vault da Firma
VAULT_PATH=~/Documents/CompanyVault

# Caminho para armazenar os dados do ChromaDB
CHROMA_PATH=~/projetos/clawdiney/chroma_db

# Modelo de Embedding (via Ollama)
MODEL_NAME=bge-m3

# Configurações do Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password123
```

**⚠️ Importante:** Aponte `VAULT_PATH` para o vault da **firma**, não para seu vault pessoal.

### 2. Configurar o Claude Code (MCP)

Para que o Claude Code use o Brain nativamente, adicione a configuração ao seu `~/.claude.json`:

```json
{
  "projects": {
    "/home/SEU_USUARIO/projetos": {
      "mcpServers": {
        "clawdiney": {
          "command": "/home/SEU_USUARIO/projetos/clawdiney/venv/bin/python3",
          "args": [
            "/home/SEU_USUARIO/projetos/clawdiney/brain_mcp_server.py"
          ]
        }
      }
    }
  }
}
```

---

## 🚀 Uso

### Iniciar Todos os Serviços

Para iniciar todos os serviços (Neo4j, ChromaDB e MCP Server) juntos:

```bash
./run_brain.sh
```

Este script irá:
- Iniciar os containers Docker para Neo4j e ChromaDB
- Aguardar a inicialização dos serviços
- Indexar o vault Obsidian
- Iniciar o servidor MCP em background

### Parar Todos os Serviços

Para parar todos os serviços, pressione Ctrl+C no terminal onde o script `run_brain.sh` está em execução, ou execute:

```bash
docker compose down
```

### Via Claude Code (Recomendado)

Com o MCP configurado, o Claude Code usará o Brain automaticamente. Basta pedir:

> *"Verifique no Brain se existe algum SOP para deploy em produção."*

> *"Pesquise no cérebro os padrões de componentes de UI do Design System."*

> *"Use a ferramenta search_brain para encontrar a estrutura de pastas dos repositórios."*

### Via Shell (Alternativo)

Se o MCP não estiver disponível, use o script direto:

```bash
./ask_brain.sh "padrões de deploy em produção"
```

### Via Python (Para desenvolvedores)

```bash
./venv/bin/python3 query_engine.py "sua consulta aqui"
```

---

## 🧩 Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                     Claude Code (Agente)                     │
└─────────────────────┬───────────────────────────────────────┘
                      │ MCP Protocol / Shell
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                   Clawdiney (Servidor)                       │
│  ┌──────────────────────┐     ┌──────────────────────────┐  │
│  │   ChromaDB (Vetor)   │     │   Neo4j (Grafo)          │  │
│  │  - Busca Semântica   │     │  - Relacionamentos       │  │
│  │  - Embeddings bge-m3 │     │  - [[WikiLinks]]         │  │
│  └──────────────────────┘     └──────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Obsidian Vault (Fonte do Conhecimento)          │
│  - SOPs, Design System, Arquitetura, Padrões                │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔄 Atualizando o Conhecimento

Sempre que o Vault da firma for atualizado (novos SOPs, padrões, etc.):

```bash
# Re-indexar o Vault
./venv/bin/python3 brain_indexer.py
```

O Claude Code terá acesso imediato às novas informações na próxima consulta.

---

## 🛡️ Privacidade e Segurança

- **Vault Pessoal vs. Vault da Firma:** Este sistema foi desenhado para usar um vault **exclusivo da firma**. Não aponte para seu vault pessoal.
- **Dados Locais:** Tudo roda localmente na sua máquina. Nada é enviado para nuvem (exceto se você usar modelos cloud via Ollama).
- **Isolamento:** Os dados do banco (Neo4j/ChromaDB) ficam em volumes Docker locais.

---

## 🐛 Troubleshooting

### O Claude Code não vê o servidor MCP
- Verifique se o `.claude.json` está configurado corretamente.
- Reinicie a sessão do Claude Code.
- Teste o servidor manualmente: `./venv/bin/python3 brain_mcp_server.py`

### Erro de conexão com Neo4j
- Verifique se o container está rodando: `docker ps | grep neo4j`
- Se necessário, reinicie: `docker compose restart`

### Erro de conexão com ChromaDB
- Verifique os logs: `docker compose logs chromadb`
- Recrie o banco (dados serão perdidos): `rm -rf chroma_db && docker compose up -d`

---

## 📚 Comandos Úteis

```bash
# Ver status dos containers
docker compose ps

# Ver logs do Neo4j
docker compose logs neo4j

# Parar todos os serviços
docker compose down

# Iniciar todos os serviços (incluindo MCP Server)
./run_brain.sh

# Re-indexar o Vault
./venv/bin/python3 brain_indexer.py

# Testar busca
./ask_brain.sh "sua consulta"
```

---

## ❓ FAQ (Perguntas Frequentes)

### "Preciso ter o Obsidian instalado?"
**Não.** O Obsidian é apenas um editor. O Brain lê os arquivos `.md` diretamente, então você só precisa dos arquivos do Vault.

### "Posso usar meu vault pessoal?"
**Tecnicamente sim, mas não recomendamos.** O sistema foi desenhado para um vault **compartilhado da firma**. Se você apontar para seu vault pessoal, seus colegas não terão acesso aos mesmos padrões.

### "Quanto tempo leva para indexar?"
Depende do tamanho do Vault:
- **Vault pequeno** (< 100 notas): ~30 segundos
- **Vault médio** (100-500 notas): 1-2 minutos
- **Vault grande** (> 500 notas): 3-5 minutos

### "Preciso re-indexar toda vez que atualizar um SOP?"
**Sim.** Sempre que o Vault mudar, rode:
```bash
./venv/bin/python3 brain_indexer.py
```

### "Funciona no Windows?"
**Sim!** Através do **WSL2** (Windows Subsystem for Linux). Siga estes passos:
1. Instale o WSL2: `wsl --install` (no PowerShell como Admin)
2. Instale o Docker Desktop para Windows e ative a integração com WSL2
3. Dentro do WSL2, siga as instruções normais de instalação como se fosse Linux

### "Qual distribuição Linux é recomendada?"
O sistema foi testado principalmente em **Ubuntu 22.04+** e **Debian 11+**, mas deve funcionar em qualquer distribuição moderna com Docker e Python 3.10+.

### "E se eu usar outro modelo que não o Qwen no Ollama?"
**Funciona normalmente.** O Brain é agnóstico ao modelo que você usa no Claude Code. O `bge-m3` é apenas para gerar embeddings (vetores), não para responder perguntas.

---

## 🤝 Contribuindo

Para adicionar novas ferramentas ao MCP:
1. Edite `brain_mcp_server.py`
2. Adicione uma nova função decorada com `@mcp.tool()`
3. Teste localmente antes de fazer commit.

---

## 📄 Licença

Uso interno da firma. Distribuição controlada.

---

**Criado com ❤️ pelo time de Engenharia**

**Versão do Kit:** v1 (2026-04-17)

**Compatibilidade:** Linux • macOS • WSL2 • Unix-like
