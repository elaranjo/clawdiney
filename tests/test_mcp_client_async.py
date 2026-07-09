#!/usr/bin/env python3
"""Simple client to test Clawdiney's MCP server."""

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
    """Test the MCP server over SSE transport."""
    try:
        # Create an SSE client to connect to the server
        async with sse_client("http://localhost:8006/mcp") as (read, write):
            async with ClientSession(read, write) as session:
                # Initialize the server
                print("🔧 Initializing MCP server...")
                result = await session.initialize()
                print(f"✅ Server initialized: {result}")

                # Test the search_brain function
                print("\n🔍 Testing search_brain function...")
                try:
                    result = await session.call_tool(
                        "search_brain", {"query": "architecture patterns"}
                    )
                    print("✅ search_brain executed successfully!")
                    content = result.content
                    if len(content) > 500:
                        content = content[:500] + "... (truncated)"
                    print(f"Result: {content}")
                except Exception as e:
                    print(f"❌ Error in search_brain: {e}")

                # Test the resolve_note function
                print("\n🔍 Testing resolve_note function...")
                try:
                    result = await session.call_tool("resolve_note", {"name": "design"})
                    print("✅ resolve_note executed successfully!")
                    content = result.content
                    print(f"Result: {content}")
                except Exception as e:
                    print(f"❌ Error in resolve_note: {e}")

                # Test the explore_graph function
                print("\n🔍 Testing explore_graph function...")
                try:
                    result = await session.call_tool(
                        "explore_graph", {"note_name": "design"}
                    )
                    print("✅ explore_graph executed successfully!")
                    content = result.content
                    if len(content) > 500:
                        content = content[:500] + "... (truncated)"
                    print(f"Result: {content}")
                except Exception as e:
                    print(f"❌ Error in explore_graph: {e}")

                # Test the get_note_chunks function
                print("\n🔍 Testing get_note_chunks function...")
                try:
                    result = await session.call_tool(
                        "get_note_chunks", {"filename": "Agent_Protocol.md"}
                    )
                    print("✅ get_note_chunks executed successfully!")
                    content = result.content
                    if len(content) > 500:
                        content = content[:500] + "... (truncated)"
                    print(f"Result: {content}")
                except Exception as e:
                    print(f"❌ Error in get_note_chunks: {e}")

        return True

    except Exception as e:
        print(f"❌ Error connecting to server: {e}")
        return False


def test_mcp_server():
    assert asyncio.run(async_test_mcp_server()) is True


if __name__ == "__main__":
    asyncio.run(async_test_mcp_server())
