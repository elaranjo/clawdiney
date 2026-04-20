#!/usr/bin/env python3
"""Script para testar a conexão com o servidor MCP do Clawdiney usando sessão persistente."""

import json
import requests
import time

class MCPClient:
    def __init__(self, base_url):
        self.base_url = base_url
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream"
        }
        self.session_id = None

    def _send_request(self, data):
        """Envia uma requisição para o servidor MCP e retorna a resposta."""
        try:
            response = requests.post(self.base_url, headers=self.headers, json=data, stream=True)
            # Ler a resposta
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode('utf-8')
                    if decoded_line.startswith('data: '):
                        json_data = decoded_line[6:]  # Remover o prefixo 'data: '
                        try:
                            result = json.loads(json_data)
                            return result
                        except json.JSONDecodeError:
                            print(f"Dados recebidos: {json_data}")
        except Exception as e:
            print(f"❌ Erro ao conectar ao servidor: {e}")
            return None

    def initialize(self):
        """Inicializa a sessão com o servidor MCP."""
        print("🔧 Inicializando sessão com servidor MCP...")
        init_data = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-04-04",
                "capabilities": {},
                "clientInfo": {
                    "name": "test-client",
                    "version": "1.0.0"
                }
            },
            "id": 1
        }

        result = self._send_request(init_data)
        if result and 'result' in result:
            print("✅ Sessão inicializada com sucesso!")
            server_info = result['result'].get('serverInfo', {})
            print(f"Informações do servidor: {server_info}")
            return True
        else:
            print(f"❌ Falha na inicialização: {result.get('error', 'Erro desconhecido') if result else 'Sem resposta'}")
            return False

    def initialized(self):
        """Envia notificação de inicialização concluída."""
        print("📡 Enviando notificação de inicialização concluída...")
        initialized_data = {
            "jsonrpc": "2.0",
            "method": "initialized",
            "params": {},
            "id": None  # Notificação, não requisição
        }

        try:
            response = requests.post(self.base_url, headers=self.headers, json=initialized_data)
            print("✅ Notificação de inicialização enviada!")
            return True
        except Exception as e:
            print(f"⚠️ Erro ao enviar notificação: {e}")
            return False

    def call_tool(self, tool_name, arguments, request_id):
        """Chama uma ferramenta no servidor MCP."""
        print(f"🔨 Chamando ferramenta: {tool_name}")
        tool_data = {
            "jsonrpc": "2.0",
            "method": "call_tool",
            "params": {
                "name": tool_name,
                "arguments": arguments
            },
            "id": request_id
        }

        result = self._send_request(tool_data)
        if result and 'result' in result:
            print(f"✅ Ferramenta {tool_name} executada com sucesso!")
            return result['result']
        elif result and 'error' in result:
            print(f"❌ Erro na ferramenta {tool_name}: {result['error']}")
            return None
        else:
            print(f"❌ Falha ao executar {tool_name}")
            return None

def main():
    """Função principal para testar o cliente MCP."""
    client = MCPClient("http://localhost:8006/mcp")

    # Etapa 1: Inicializar sessão
    if not client.initialize():
        return

    # Etapa 2: Enviar notificação de inicialização concluída
    client.initialized()

    # Etapa 3: Testar a função search_brain
    result = client.call_tool("search_brain", {"query": "architecture patterns"}, 2)
    if result:
        content = result.get('content', '')
        if len(content) > 500:
            content = content[:500] + "... (truncado)"
        print(f"Resultado da busca: {content}")

    # Etapa 4: Testar a função resolve_note
    result = client.call_tool("resolve_note", {"name": "design"}, 3)
    if result:
        content = result.get('content', '')
        print(f"Resultado do resolve_note: {content}")

    # Etapa 5: Testar a função explore_graph
    result = client.call_tool("explore_graph", {"note_name": "design"}, 4)
    if result:
        content = result.get('content', '')
        print(f"Resultado do explore_graph: {content}")

    # Etapa 6: Testar a função get_note_chunks
    result = client.call_tool("get_note_chunks", {"filename": "Agent_Protocol.md"}, 5)
    if result:
        content = result.get('content', '')
        if len(content) > 500:
            content = content[:500] + "... (truncado)"
        print(f"Resultado do get_note_chunks: {content}")

    print("\n✅ Todos os testes concluídos!")

if __name__ == "__main__":
    main()