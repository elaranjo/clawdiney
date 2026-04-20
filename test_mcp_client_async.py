#!/usr/bin/env python3
"""Cliente simples para testar o servidor MCP do Clawdiney."""

import asyncio
import sys
from mcp import ClientSession
from mcp.client.sse import sse_client

async def test_mcp_server():
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
                    result = await session.call_tool("search_brain", {"query": "architecture patterns"})
                    print(f"✅ Função search_brain executada com sucesso!")
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
                    print(f"✅ Função resolve_note executada com sucesso!")
                    content = result.content
                    print(f"Resultado: {content}")
                except Exception as e:
                    print(f"❌ Erro na função resolve_note: {e}")

                # Testar a função explore_graph
                print("\n🔍 Testando função explore_graph...")
                try:
                    result = await session.call_tool("explore_graph", {"note_name": "design"})
                    print(f"✅ Função explore_graph executada com sucesso!")
                    content = result.content
                    if len(content) > 500:
                        content = content[:500] + "... (truncado)"
                    print(f"Resultado: {content}")
                except Exception as e:
                    print(f"❌ Erro na função explore_graph: {e}")

                # Testar a função get_note_chunks
                print("\n🔍 Testando função get_note_chunks...")
                try:
                    result = await session.call_tool("get_note_chunks", {"filename": "Agent_Protocol.md"})
                    print(f"✅ Função get_note_chunks executada com sucesso!")
                    content = result.content
                    if len(content) > 500:
                        content = content[:500] + "... (truncado)"
                    print(f"Resultado: {content}")
                except Exception as e:
                    print(f"❌ Erro na função get_note_chunks: {e}")

    except Exception as e:
        print(f"❌ Erro ao conectar ao servidor: {e}")
        return False

    print("\n✅ Todos os testes concluídos!")
    return True

if __name__ == "__main__":
    asyncio.run(test_mcp_server())