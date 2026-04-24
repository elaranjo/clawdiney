# Project Watcher - Auto-Sync para Obsidian

## Visão Geral

O Project Watcher é um serviço que monitora automaticamente mudanças nos seus projetos e atualiza a documentação no Obsidian em tempo real.

## Por que usar?

**Problema:** Durante o trabalho diário, é fácil esquecer de sincronizar manualmente as alterações do código com o Obsidian.

**Solução:** O watcher roda em background e detecta automaticamente mudanças nos arquivos, reindexando projetos afetados após um debounce de 10 segundos.

## Instalação Rápida

### Opção 1: Scripts de controle (Recomendado para desenvolvimento)

```bash
# Iniciar o watcher
./scripts/start_watcher.sh

# Parar o watcher
./scripts/stop_watcher.sh

# Ver logs em tempo real
tail -f logs/watcher.log
```

### Opção 2: Serviço systemd (Produção / Auto-start)

```bash
# Instalar serviço
sudo cp scripts/clawdiney-watcher.service /etc/systemd/system/

# Habilitar e iniciar
sudo systemctl daemon-reload
sudo systemctl enable clawdiney-watcher
sudo systemctl start clawdiney-watcher

# Verificar status
sudo systemctl status clawdiney-watcher

# Ver logs via journalctl
journalctl -u clawdiney-watcher -f
```

## Como Funciona

### Arquivos Monitorados

O watcher detecta mudanças em arquivos com estas extensões:
- `.py`, `.ts`, `.js`, `.tsx`, `.jsx` - Código
- `.json`, `.toml`, `.yaml`, `.yml` - Configuração
- `.md`, `.txt` - Documentação
- `.sql`, `.prisma`, `.graphql` - Banco de dados

### Prioridade Alta

Estes arquivos sempre disparam reindexação imediata:
- `package.json`
- `pyproject.toml`
- `setup.py`
- `requirements.txt`
- `Cargo.toml`
- `go.mod`
- `tsconfig.json`
- `docker-compose.yml`

### Diretórios Ignorados

Estes diretórios são automaticamente ignorados:
- `__pycache__`, `.venv`, `venv`
- `node_modules`
- `.git`, `.github`
- `dist`, `build`, `coverage`
- `target`, `vendor`
- Arquivos ocultos (`.hidden`)

### Debounce

Mudanças rápidas são agrupadas:
- **Debounce:** 10 segundos após a última mudança
- **Batch:** Mudanças dentro de 2 segundos são tratadas como um lote

## Exemplo de Uso

1. **Inicie o watcher:**
   ```bash
   ./scripts/start_watcher.sh
   ```

2. **Trabalhe normalmente no seu código**

3. **O watcher detecta e sincroniza automaticamente:**
   ```
   2026-04-24 13:45:27 [INFO] 🔴 High-priority change in meu-projeto - will reindex soon
   2026-04-24 13:45:37 [INFO] 🔄 Reindexing projects: meu-projeto
   2026-04-24 13:45:40 [INFO] ✅ Updated: meu-projeto
   ```

4. **Verifique a documentação atualizada no Obsidian:**
   - Arquivo: `00_Inbox/Projetos/meu-projeto.md`

## Configuração

### Mudar o diretório de projetos

Edite `scripts/start_watcher.sh`:
```bash
PROJECTS_ROOT="${PROJECTS_ROOT:-$HOME/Documentos/projetos}"
```

Ou defina a variável de ambiente:
```bash
export PROJECTS_ROOT=~/meus-projetos
./scripts/start_watcher.sh
```

### Mudar o diretório do Obsidian

Edite `scripts/clawdiney-watcher.service` ou passe via linha de comando:
```bash
./venv/bin/python3 -m clawdiney.scripts.watch_projects ~/projetos --vault ~/MeuObsidian
```

## Troubleshooting

### Watcher não inicia

Verifique se o virtual environment está ativo:
```bash
ls -la venv/bin/python3
```

### Logs mostram erros de caminho

Verifique se os diretórios existem:
```bash
ls -la ~/Documentos/projetos
ls -la ~/Documents/ObsidianVault
```

### Watcher consumindo muita CPU

Verifique se não está monitorando diretórios com muitas mudanças:
```bash
tail -f logs/watcher.log | grep "Change detected"
```

Se necessário, adicione mais diretórios à lista `IGNORE_DIRS` em `src/clawdiney/scripts/watch_projects.py`.

### Parar serviço systemd

```bash
sudo systemctl stop clawdiney-watcher
sudo systemctl disable clawdiney-watcher
```

## Arquitetura

```
┌─────────────────────────────────────────────────────────────┐
│                    Project Watcher                          │
├─────────────────────────────────────────────────────────────┤
│  FileSystemEventHandler (watchdog)                          │
│  │                                                          │
│  ├── on_modified() ──┐                                      │
│  ├── on_created()  ──┼──> _schedule_reindex() ──┐          │
│  └── on_deleted()  ──┘                          │          │
│                                                 ▼          │
│  Background Loop:                                      │
│  ┌──────────────────────────────────────────────────┐    │
│  │  A cada 1 segundo:                               │    │
│  │  1. Verifica projetos pendentes                  │    │
│  │  2. Aplica debounce (10s)                        │    │
│  │  3. Chama ProjectIndexer para reindexar          │    │
│  │  4. Salva .md no Obsidian                        │    │
│  └──────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Comandos Úteis

```bash
# Ver se está rodando
ps aux | grep watch_projects

# Ver PID
cat logs/watcher.pid

# Restartar
./scripts/stop_watcher.sh && ./scripts/start_watcher.sh

# Logs das últimas 100 linhas
tail -100 logs/watcher.log
```
