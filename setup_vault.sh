#!/bin/bash
# OpenClaw Vault - Setup Bootstrapper
# This script creates a standardized Obsidian Vault structure for the company

set -e  # Exit on error

echo "🧠 OpenClaw Vault - Setup Bootstrapper"
echo "======================================"
echo ""

# 1. Ask for Vault location
echo "📁 Where should we create your Obsidian Vault?"
echo "   Default: ~/Documents/CompanyVault"
read -p "Enter path (or press Enter for default): " VAULT_PATH
VAULT_PATH="${VAULT_PATH:-$HOME/Documents/CompanyVault}"

# Expand ~ to full path
VAULT_PATH=$(eval echo "$VAULT_PATH")

echo ""
echo "📁 Vault will be created at: $VAULT_PATH"
echo ""

# 2. Check if directory already exists
if [ -d "$VAULT_PATH" ]; then
    echo "⚠️  Directory already exists at: $VAULT_PATH"
    read -p "Do you want to continue? This may overwrite existing files. (y/n): " confirm
    if [[ ! $confirm =~ ^[Yy]$ ]]; then
        echo "❌ Aborted."
        exit 1
    fi
fi

# 3. Create directory structure
echo "📁 Creating directory structure..."
mkdir -p "$VAULT_PATH"
mkdir -p "$VAULT_PATH/00_Inbox"
mkdir -p "$VAULT_PATH/10_Projects"
mkdir -p "$VAULT_PATH/20_Areas"
mkdir -p "$VAULT_PATH/30_Resources"
mkdir -p "$VAULT_PATH/30_Resources/SOPs"
mkdir -p "$VAULT_PATH/30_Resources/Templates"
mkdir -p "$VAULT_PATH/40_Archives"
mkdir -p "$VAULT_PATH/50_Daily"
mkdir -p "$VAULT_PATH/60_System"
echo "✅ Directory structure created"

# 4. Create 00_Index.md
echo "📝 Creating 00_Index.md..."
cat > "$VAULT_PATH/00_Index.md" << 'EOF'
# 🧠 Company Vault - Index

Bem-vindo ao **Company Vault** — a base de conhecimento centralizada da nossa firma.

---

## 📋 Como Este Vault Funciona

Este vault segue a metodologia **P.A.R.A.** (Projects, Areas, Resources, Archives) com adaptações para engenharia de software.

### 🎯 Propósito

- **Centralizar conhecimento:** Todo o know-how da firma está aqui
- **Padronizar processos:** SOPs claros e acessíveis
- **Facilitar onboarding:** Novos devs encontram tudo que precisam
- **Integrar com IA:** Este vault alimenta o **Clawdiney** (nosso sistema de RAG)

---

## 📁 Estrutura de Pastas

```
CompanyVault/
├── 00_Inbox/          # Coisas não organizadas ainda (bandeja de entrada)
├── 10_Projects/       # Projetos ativos (com prazo e escopo definidos)
├── 20_Areas/          # Áreas de responsabilidade contínua (ex: DevOps, QA)
├── 30_Resources/      # Recursos de conhecimento (SOPs, Templates, Referências)
│   ├── SOPs/          # Procedimentos Operacionais Padrão
│   └── Templates/     # Modelos de documentos
├── 40_Archives/       # Projetos e recursos arquivados (inativos)
├── 50_Daily/          # Notas diárias (daily notes)
└── 60_System/         # Configurações do vault, metadados, etc.
```

---

## 🔗 Como Usar

### 1. **Sempre comece pelo Inbox**
Nova ideia, tarefa ou informação? Jogue em `00_Inbox/` e organize depois.

### 2. **Use Links Bidirecionais**
Conecte notas com `[[Nome da Nota]]`. Isso alimenta o **grafo de conhecimento** do Clawdiney.

### 3. **Siga os SOPs**
Antes de implementar algo, consulte `30_Resources/SOPs/` para ver se já existe um padrão.

### 4. **Mantenha Organizado**
- Inbox → Organize semanalmente
- Projects → Arquive quando concluir
- Resources → Atualize quando aprender algo novo

---

## 🤖 Integração com Clawdiney

Este vault é indexado pelo **Clawdiney**, que permite:
- **Busca semântica:** Encontre informações por significado, não apenas palavras-chave
- **Grafo de conhecimento:** Descubra conexões entre notas via `[[links]]`
- **IA contextual:** O Claude Code consulta este vault antes de sugerir código

### 📊 O Que o Brain Indexa

| Tipo de Nota | Indexado? | Observações |
|--------------|-----------|-------------|
| SOPs | ✅ Sim | Prioridade máxima |
| Design System | ✅ Sim | Componentes e padrões de UI |
| Arquitetura | ✅ Sim | Decisões técnicas e ADRs |
| Daily Notes | ⚠️ Opcional | Só se tiver conhecimento relevante |
| Pessoal | ❌ Não | Use outro vault para notas pessoais |

---

## 📝 Templates

Use os templates em `30_Resources/Templates/` para padronizar:

- `SOP_Template.md` → Para criar novos SOPs
- `Project_Template.md` → Para iniciar novos projetos
- `Meeting_Notes.md` → Para atas de reunião
- `ADR_Template.md` → Para Architecture Decision Records

---

## 🚀 Primeiros Passos

1. **Leia os SOPs existentes** em `30_Resources/SOPs/`
2. **Configure o Clawdiney** (veja `README.md` no repositório)
3. **Comece a usar!** Crie notas, linkie informações, consulte o Brain

---

## 📚 Recursos Adicionais

- **Clawdiney Repo:** [link para o repositório]
- **Documentação do Obsidian:** https://help.obsidian.md/
- **Método P.A.R.A.:** https://fortelabs.com/blog/para/

---

**Última atualização:** 2026-04-17
**Versão do Vault:** v1.0

---

*"Conhecimento não usado é apenas dados. Conhecimento organizado é poder."*
EOF
echo "✅ 00_Index.md created"

# 5. Create basic SOPs
echo "📝 Creating basic SOPs..."

# SOP_Template.md
cat > "$VAULT_PATH/30_Resources/SOPs/SOP_Template.md" << 'EOF'
# SOP: [Nome do Procedimento]

**ID:** SOP-XXX
**Última atualização:** YYYY-MM-DD
**Responsável:** [Nome/Time]

---

## 🎯 Objetivo

[Descreva qual problema este SOP resolve ou qual processo ele padroniza]

---

## 📋 Escopo

**Aplica-se a:**
- [Quem deve seguir este SOP]
- [Quais projetos/situações]

**Não se aplica a:**
- [Exceções]

---

## 🛠️ Procedimento

### Passo 1: [Nome do Passo]
[Descrição detalhada do que fazer]

```bash
# Exemplo de comando, se aplicável
comando --aqui
```

### Passo 2: [Nome do Passo]
[Descrição detalhada]

### Passo 3: [Nome do Passo]
[Descrição detalhada]

---

## ✅ Definition of Done (DoD)

Este SOP foi seguido corretamente quando:
- [ ] Critério 1
- [ ] Critério 2
- [ ] Critério 3

---

## 📚 Referências

- [[Nota Relacionada 1]]
- [[Nota Relacionada 2]]
- [Link externo, se aplicável]

---

## 🔄 Histórico de Mudanças

| Data | Versão | Mudança | Autor |
|------|--------|---------|-------|
| YYYY-MM-DD | 1.0 | Criação inicial | [Nome] |
EOF

# SOP_Backend_Repos.md
cat > "$VAULT_PATH/30_Resources/SOPs/SOP_Backend_Repos.md" << 'EOF'
# SOP: Estrutura de Repositórios Backend

**ID:** SOP-001
**Última atualização:** 2026-04-17
**Responsável:** Time de Backend

---

## 🎯 Objetivo

Padronizar a estrutura e localização de todos os repositórios backend da firma.

---

## 📋 Escopo

**Aplica-se a:**
- Todos os microsserviços backend
- SDKs e bibliotecas internas
- APIs e gateways

---

## 📁 Estrutura de Pastas

Todos os repositórios de backend devem residir em: `~/projetos/`

### Estrutura Padrão do Repositório

```
nome-servico/
├── src/
├── tests/
├── docker/
├── docs/
├── CLAUDE.md          # Instruções para o Claude Code
├── README.md
└── docker-compose.yml
```

---

## 🛠️ Procedimento

### Passo 1: Criar Repositório
1. Crie no GitHub/GitLab da firma
2. Use naming convention: `nome-servico` (kebab-case)

### Passo 2: Clonar Localmente
```bash
cd ~/projetos
git clone git@github.com:[FIRMA]/nome-servico.git
```

### Passo 3: Configurar CLAUDE.md
Adicione instruções específicas do projeto para o Claude Code.

---

## ✅ Definition of Done (DoD)

- [ ] Repositório criado no GitHub/GitLab
- [ ] CLAUDE.md configurado
- [ ] README.md com instruções básicas
- [ ] Docker Compose funcional

---

## 📚 Referências

- [[SOP_Frontend_Repos]]
- [[SOP_Docker_Padrao]]
- [[CLAUDE_MD_Protocol]]

---

## 🔄 Histórico de Mudanças

| Data | Versão | Mudança | Autor |
|------|--------|---------|-------|
| 2026-04-17 | 1.0 | Criação inicial | Claudinei |
EOF

# SOP_Design_System.md
cat > "$VAULT_PATH/30_Resources/SOPs/SOP_Design_System.md" << 'EOF'
# SOP: Design System e Componentes de UI

**ID:** SOP-002
**Última atualização:** 2026-04-17
**Responsável:** Time de Frontend

---

## 🎯 Objetivo

Padronizar o uso de componentes de UI em todos os projetos da firma.

---

## 📋 Regra de Ouro

> **NUNCA crie componentes de UI do zero sem consultar o Design System.**

Sempre verifique se já existe um componente que atende sua necessidade.

---

## 🛠️ Procedimento

### Passo 1: Consultar o Design System
Antes de criar qualquer UI:
1. Consulte a documentação do Design System
2. Verifique se o componente já existe
3. Se não existir, avalie se vale a pena criar

### Passo 2: Usar Componentes Existentes
```tsx
// ✅ Correto: Usar componente do DS
import { Button } from '@firma/design-system'

// ❌ Errado: Criar componente próprio
const MeuButton = () => <button className="...">
```

### Passo 3: Propor Novos Componentes
Se precisar de um componente novo:
1. Crie uma issue no repositório do Design System
2. Documente o caso de uso
3. Aguarde aprovação do time de Frontend

---

## ✅ Definition of Done (DoD)

- [ ] Componentes do DS usados sempre que possível
- [ ] Novos componentes aprovados pelo time
- [ ] Documentação atualizada

---

## 📚 Referências

- [[SOP_Frontend_Repos]]
- [Link para o Figma do Design System]
- [Link para o Storybook]

---

## 🔄 Histórico de Mudanças

| Data | Versão | Mudança | Autor |
|------|--------|---------|-------|
| 2026-04-17 | 1.0 | Criação inicial | Claudinei |
EOF

echo "✅ Basic SOPs created"

# 6. Create Agent_Protocol.md
echo "📝 Creating Agent_Protocol.md..."
cat > "$VAULT_PATH/60_System/Agent_Protocol.md" << 'EOF'
# 🤖 Agent Protocol

Protocolo para agentes de IA (Claude Code, Claudinei, etc.) que operam neste vault.

---

## 🔍 Consulta de Conhecimento

Antes de sugerir uma solução ou criar uma nota, os agentes **devem** realizar a seguinte sequência de busca:

1. **Verificar `30_Resources/SOPs/`** para conceitos técnicos e procedimentos
2. **Verificar `10_Projects/`** para status de tarefas e contexto do projeto
3. **Consultar `00_Index.md`** para entender a hierarquia atual
4. **Usar o Clawdiney** para busca semântica no vault completo

---

## 📝 Criação de Notas

Ao criar novas notas:

1. **Use o template apropriado** (em `30_Resources/Templates/`)
2. **Adicione links bidirecionais** `[[Nome da Nota]]` para notas relacionadas
3. **Coloque na pasta correta** (não deixe no Inbox)
4. **Atualize o índice** se criar uma nova categoria

---

## 🧠 Integração com Clawdiney

Os agentes devem:

1. **Sempre consultar o Brain** antes de implementar código
2. **Seguir SOPs encontrados** como verdade absoluta
3. **Sugerir atualizações** se encontrarem inconsistências entre código e documentação

---

## 🔄 Atualização de Conhecimento

Quando um agente aprender algo novo:

1. **Documente imediatamente** no vault
2. **Crie ou atualize o SOP** correspondente
3. **Notifique o time** sobre a atualização

---

**Versão:** 1.0 (2026-04-17)
EOF
echo "✅ Agent_Protocol.md created"

# 7. Initialize Git (optional)
echo ""
read -p "Do you want to initialize a Git repository? (y/n): " init_git
if [[ $init_git =~ ^[Yy]$ ]]; then
    echo "🔧 Initializing Git repository..."
    cd "$VAULT_PATH"
    git init
    echo "# Company Vault" > README.md
    echo "" >> README.md
    echo "Centralized knowledge base for the company." >> README.md
    echo "" >> README.md
    echo "## Structure" >> README.md
    echo "" >> README.md
    echo "See [[00_Index]] for documentation." >> README.md
    
    # Create .gitignore
    cat > .gitignore << 'EOF'
# Obsidian
.obsidian/

# OS
.DS_Store
Thumbs.db

# Logs
*.log

# Temp
*.tmp
EOF
    
    git add .
    git commit -m "📚 Initial commit: Company Vault structure"
    echo "✅ Git repository initialized"
    echo ""
    echo "📌 Next steps:"
    echo "   1. Create a repository on GitHub/GitLab"
    echo "   2. Add the remote: git remote add origin git@github.com:[FIRMA]/company-vault.git"
    echo "   3. Push: git push -u origin main"
else
    echo "⏭️  Skipping Git initialization"
fi

# 8. Final summary
echo ""
echo "======================================"
echo "🎉 OpenClaw Vault Setup Complete!"
echo "======================================"
echo ""
echo "📁 Vault location: $VAULT_PATH"
echo ""
echo "📚 What was created:"
echo "   ✅ Directory structure (P.A.R.A. method)"
echo "   ✅ 00_Index.md (vault documentation)"
echo "   ✅ SOP_Template.md"
echo "   ✅ SOP_Backend_Repos.md"
echo "   ✅ SOP_Design_System.md"
echo "   ✅ Agent_Protocol.md"
echo ""
echo "🚀 Next steps:"
echo "   1. Open this vault in Obsidian"
echo "   2. Read the 00_Index.md for guidance"
echo "   3. Run setup_brain.sh to connect the Brain"
echo ""
echo "📚 For more information, see 00_Index.md inside the vault"
echo ""
