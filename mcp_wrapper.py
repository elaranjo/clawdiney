#!/usr/bin/env python3
"""Wrapper mínimo para iniciar o servidor MCP no container."""

import os
import sys
from pathlib import Path


def main():
    print("🚀 Iniciando wrapper do servidor MCP do Clawdiney...", flush=True)
    transport = os.environ.get("MCP_TRANSPORT", "stdio")
    mount_path = os.environ.get("MCP_MOUNT_PATH")

    # Verificar se o vault existe
    vault_path = os.environ.get("VAULT_PATH", "/vault")
    if not Path(vault_path).exists():
        print(f"⚠️  Caminho do Vault não encontrado: {vault_path}", flush=True)

    # Verificar se o modelo Ollama está disponível
    try:
        model_name = os.environ.get("MODEL_NAME", "bge-m3:latest")
        print(f"🔍 Verificando modelo Ollama: {model_name}", flush=True)
    except Exception as e:
        print(f"⚠️  Aviso: Problema ao verificar modelo Ollama: {e}", flush=True)

    # Importar e executar o servidor MCP
    try:
        print("🔧 Importando módulo do servidor MCP...", flush=True)
        from brain_mcp_server import mcp

        print(f"🔌 Iniciando servidor MCP com transporte {transport}...", flush=True)
        mcp.run(transport=transport, mount_path=mount_path)

    except KeyboardInterrupt:
        print("🛑 Servidor MCP interrompido pelo usuário", flush=True)
        sys.exit(0)
    except Exception as e:
        print(f"❌ Erro ao iniciar servidor MCP: {e}", flush=True)
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
