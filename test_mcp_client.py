#!/usr/bin/env python3
"""Script para testar a conexão com o servidor MCP do Clawdiney."""

import json

import requests


def send_request(url, headers, data):
    """Envia uma requisição para o servidor MCP e retorna a resposta."""
    try:
        response = requests.post(url, headers=headers, json=data, stream=True)
        # Ler a resposta
        for line in response.iter_lines():
            if line:
                decoded_line = line.decode("utf-8")
                if decoded_line.startswith("data: "):
                    json_data = decoded_line[6:]  # Remover o prefixo 'data: '
                    try:
                        result = json.loads(json_data)
                        return result
                    except json.JSONDecodeError:
                        print(f"Dados recebidos: {json_data}")
    except Exception as e:
        print(f"❌ Erro ao conectar ao servidor: {e}")
        return None


def test_mcp_server():
    """Testa a conexão com o servidor MCP e suas funções."""
    url = "http://localhost:8006/mcp"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    # Etapa 1: Inicializar o servidor
    print("🔧 Inicializando servidor MCP...")
    init_data = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-04-04",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0.0"},
        },
        "id": 1,
    }

    result = send_request(url, headers, init_data)
    if not result or "error" in result:
        print(f"❌ Falha na inicialização: {result.get('error', 'Erro desconhecido')}")
        return False

    print("✅ Servidor inicializado com sucesso!")
    print(
        f"Informações do servidor: {json.dumps(result['result']['serverInfo'], indent=2)}"
    )

    # Etapa 2: Enviar notificação de inicialização concluída
    print("\n📡 Enviando notificação de inicialização concluída...")
    initialized_data = {"jsonrpc": "2.0", "method": "initialized", "params": {}}

    # Para notificações, o ID deve ser null
    initialized_data["id"] = None

    try:
        requests.post(url, headers=headers, json=initialized_data)
        print("✅ Notificação de inicialização enviada!")
    except Exception as e:
        print(f"⚠️ Erro ao enviar notificação (pode ser esperado): {e}")

    # Etapa 3: Testar a função search_brain
    print("\n🔍 Testando função search_brain...")
    search_data = {
        "jsonrpc": "2.0",
        "method": "call_tool",
        "params": {
            "name": "search_brain",
            "arguments": {"query": "architecture patterns"},
        },
        "id": 2,
    }

    result = send_request(url, headers, search_data)
    if result and "result" in result:
        print("✅ Função search_brain executada com sucesso!")
        # Limitar a saída para não ficar muito longa
        output = result["result"].get("content", "")
        if len(output) > 500:
            output = output[:500] + "... (truncado)"
        print(f"Resultado da busca: {output}")
    elif result and "error" in result:
        print(f"❌ Erro na função search_brain: {result['error']}")
    else:
        print("❌ Falha ao executar search_brain")

    # Etapa 4: Testar a função resolve_note
    print("\n🔍 Testando função resolve_note...")
    resolve_data = {
        "jsonrpc": "2.0",
        "method": "call_tool",
        "params": {"name": "resolve_note", "arguments": {"name": "design"}},
        "id": 3,
    }

    result = send_request(url, headers, resolve_data)
    if result and "result" in result:
        print("✅ Função resolve_note executada com sucesso!")
        print(f"Resultado: {result['result'].get('content', '')}")
    elif result and "error" in result:
        print(f"❌ Erro na função resolve_note: {result['error']}")
    else:
        print("❌ Falha ao executar resolve_note")

    print("\n✅ Todos os testes concluídos!")


if __name__ == "__main__":
    test_mcp_server()
