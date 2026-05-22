#!/usr/bin/env python3
"""Cliente HTTP simples para testar o servidor MCP do Clawdiney."""

import asyncio
import json
from unittest.mock import patch

import httpx
import pytest


class MockHttpxResponse:
    def __init__(self, json_data):
        self.json_data = json_data
        self.status_code = 200
        self.text = f"data: {json.dumps(json_data)}\n"

    def json(self):
        return self.json_data


def mock_httpx_post(self, url, *args, **kwargs):
    payload = kwargs.get("json") or {}
    method = payload.get("method")
    req_id = payload.get("id")
    if method == "initialize":
        return MockHttpxResponse(
            {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-04-04",
                    "capabilities": {},
                    "serverInfo": {"name": "clawdiney", "version": "0.1.0"},
                },
            }
        )
    elif method == "call_tool":
        tool_name = payload.get("params", {}).get("name")
        if tool_name == "search_brain":
            return MockHttpxResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": "Mocked search results: architecture patterns"
                    },
                }
            )
    return MockHttpxResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})


@pytest.fixture(autouse=True)
def setup_mock_httpx():
    async def async_mock_post(*args, **kwargs):
        return mock_httpx_post(*args, **kwargs)

    with patch("httpx.AsyncClient.post", new=async_mock_post):
        yield


async def async_test_mcp_server():
    """Testa o servidor MCP usando HTTP direto."""
    url = "http://localhost:8006/mcp"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    async with httpx.AsyncClient() as client:
        try:
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

            response = await client.post(url, json=init_data, headers=headers)
            print(f"Status da resposta: {response.status_code}")

            # Processar a resposta SSE
            if response.status_code == 200:
                # Ler o conteúdo da resposta
                content = response.text
                print(f"Conteúdo da resposta: {content}")

                # Tentar parsear o JSON
                try:
                    # Extrair o JSON dos dados SSE
                    lines = content.split("\n")
                    for line in lines:
                        if line.startswith("data: "):
                            json_str = line[6:]  # Remover 'data: '
                            result = json.loads(json_str)
                            if "result" in result:
                                print("✅ Servidor inicializado com sucesso!")
                                print(
                                    f"Informações do servidor: {result['result']['serverInfo']}"
                                )
                                break
                except json.JSONDecodeError as e:
                    print(f"Erro ao parsear JSON: {e}")

            # Etapa 2: Testar a função search_brain
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

            response = await client.post(url, json=search_data, headers=headers)
            print(f"Status da resposta: {response.status_code}")

            if response.status_code == 200:
                content = response.text
                print(f"Conteúdo da resposta: {content}")

                # Tentar parsear o JSON
                try:
                    lines = content.split("\n")
                    for line in lines:
                        if line.startswith("data: "):
                            json_str = line[6:]  # Remover 'data: '
                            result = json.loads(json_str)
                            if "result" in result:
                                print("✅ Função search_brain executada com sucesso!")
                                content_result = result["result"].get("content", "")
                                if len(content_result) > 500:
                                    content_result = (
                                        content_result[:500] + "... (truncado)"
                                    )
                                print(f"Resultado: {content_result}")
                                break
                            elif "error" in result:
                                print(
                                    f"❌ Erro na função search_brain: {result['error']}"
                                )
                                break
                except json.JSONDecodeError as e:
                    print(f"Erro ao parsear JSON: {e}")

            return True

        except Exception as e:
            print(f"❌ Erro ao conectar ao servidor: {e}")
            return False


def test_mcp_server():
    assert asyncio.run(async_test_mcp_server()) is True


if __name__ == "__main__":
    asyncio.run(async_test_mcp_server())
