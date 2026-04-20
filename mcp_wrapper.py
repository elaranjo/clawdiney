#!/usr/bin/env python3
"""
Wrapper para o servidor MCP do Clawdiney que permite execução em container Docker.
Este script atua como um proxy entre o protocolo MCP e o servidor FastMCP.
"""

import os
import sys
import json
import asyncio
import subprocess
from pathlib import Path

async def main():
    """Main function to run the MCP server wrapper"""
    print("🚀 Iniciando wrapper do servidor MCP do Clawdiney...", flush=True)

    # Verificar se o vault existe
    vault_path = os.environ.get('VAULT_PATH', '/vault')
    if not Path(vault_path).exists():
        print(f"⚠️  Caminho do Vault não encontrado: {vault_path}", flush=True)

    # Verificar se o modelo Ollama está disponível
    try:
        import ollama
        model_name = os.environ.get('MODEL_NAME', 'bge-m3:latest')
        print(f"🔍 Verificando modelo Ollama: {model_name}", flush=True)
        # Esta chamada pode falhar se o modelo não estiver disponível
        # ollama.list()  # Descomentar se quiser verificar a lista de modelos
    except Exception as e:
        print(f"⚠️  Aviso: Problema ao verificar modelo Ollama: {e}", flush=True)

    # Importar e executar o servidor MCP
    try:
        print("🔧 Importando módulo do servidor MCP...", flush=True)
        from brain_mcp_server import mcp

        print("🔌 Iniciando servidor MCP...", flush=True)
        # Executar o servidor no modo padrão (stdio)
        mcp.run()

    except KeyboardInterrupt:
        print("🛑 Servidor MCP interrompido pelo usuário", flush=True)
        sys.exit(0)
    except Exception as e:
        print(f"❌ Erro ao iniciar servidor MCP: {e}", flush=True)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())