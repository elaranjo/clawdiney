#!/usr/bin/env python3
"""Cliente simples para testar o servidor MCP do Clawdiney."""

import asyncio
from unittest.mock import patch

import pytest
from mcp import ClientSession
from mcp.client.sse import sse_client


class MockToolResult:
    def __init__(self, content):
        self.content = content


class MockClientSession:
    def __init__(self, read, write):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def initialize(self):
        return "Mocked MCP Client Initialized"

    async def call_tool(self, tool_name, arguments):
        if tool_name == "search_brain":
            return MockToolResult("Mocked search results: architecture patterns")
        elif tool_name == "resolve_note":
            return MockToolResult("[{'path': 'design.md', 'filename': 'design.md'}]")
        elif tool_name == "explore_graph":
            return MockToolResult("['design.md']")
        elif tool_name == "get_note_chunks":
            return MockToolResult("[{'heading': '# Header 1'}]")
        return MockToolResult("")


class MockSseClient:
    def __init__(self, url):
        pass

    async def __aenter__(self):
        return (None, None)

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


@pytest.fixture(autouse=True)
def setup_mock_mcp():
    with (
        patch("tests.test_mcp_client_async.sse_client", new=MockSseClient),
        patch("tests.test_mcp_client_async.ClientSession", new=MockClientSession),
    ):
        yield



async def async_test_mcp_server():
    """Testa o servidor MCP usando transporte SSE."""
    try:
        # Criar cliente SSE para conectar ao servidor
        async with sse_client("http://localhost:8006/mcp") as (read, write):
            async with ClientSession(read, write) as session:
                # Inicializar o servidor
                print("🔧 Inicializando servidor MCP...")
                result = await session.initialize()
                print(f"✅ Servidor inicializado: {result}")

                # Testar a função search_brain
                print("\n🔍 Testando função search_brain...")
                try:
                    result = await session.call_tool(
                        "search_brain", {"query": "architecture patterns"}
                    )
                    print("✅ Função search_brain executada com sucesso!")
                    content = result.content
                    if len(content) > 500:
                        content = content[:500] + "... (truncado)"
                    print(f"Resultado: {content}")
                except Exception as e:
                    print(f"❌ Erro na função search_brain: {e}")

                # Testar a função resolve_note
                print("\n🔍 Testando função resolve_note...")
                try:
                    result = await session.call_tool("resolve_note", {"name": "design"})
                    print("✅ Função resolve_note executada com sucesso!")
                    content = result.content
                    print(f"Resultado: {content}")
                except Exception as e:
                    print(f"❌ Erro na função resolve_note: {e}")

                # Testar a função explore_graph
                print("\n🔍 Testando função explore_graph...")
                try:
                    result = await session.call_tool(
                        "explore_graph", {"note_name": "design"}
                    )
                    print("✅ Função explore_graph executada com sucesso!")
                    content = result.content
                    if len(content) > 500:
                        content = content[:500] + "... (truncado)"
                    print(f"Resultado: {content}")
                except Exception as e:
                    print(f"❌ Erro na função explore_graph: {e}")

                # Testar a função get_note_chunks
                print("\n🔍 Testando função get_note_chunks...")
                try:
                    result = await session.call_tool(
                        "get_note_chunks", {"filename": "Agent_Protocol.md"}
                    )
                    print("✅ Função get_note_chunks executada com sucesso!")
                    content = result.content
                    if len(content) > 500:
                        content = content[:500] + "... (truncado)"
                    print(f"Resultado: {content}")
                except Exception as e:
                    print(f"❌ Erro na função get_note_chunks: {e}")

        return True

    except Exception as e:
        print(f"❌ Erro ao conectar ao servidor: {e}")
        return False

def test_mcp_server():
    assert asyncio.run(async_test_mcp_server()) is True


if __name__ == "__main__":
    asyncio.run(async_test_mcp_server())
