#!/usr/bin/env python3
"""Script to test the connection to Clawdiney's MCP server using a persistent session."""

import json

import requests


class MCPClient:
    def __init__(self, base_url):
        self.base_url = base_url
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        }
        self.session_id = None

    def _send_request(self, data):
        """Send a request to the MCP server and return the response."""
        try:
            response = requests.post(
                self.base_url, headers=self.headers, json=data, stream=True
            )
            # Read the response
            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode("utf-8")
                    if decoded_line.startswith("data: "):
                        json_data = decoded_line[6:]  # Strip the 'data: ' prefix
                        try:
                            result = json.loads(json_data)
                            return result
                        except json.JSONDecodeError:
                            print(f"Data received: {json_data}")
        except Exception as e:
            print(f"❌ Error connecting to server: {e}")
            return None

    def initialize(self):
        """Initialize the session with the MCP server."""
        print("🔧 Initializing session with MCP server...")
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

        result = self._send_request(init_data)
        if result and "result" in result:
            print("✅ Session initialized successfully!")
            server_info = result["result"].get("serverInfo", {})
            print(f"Server info: {server_info}")
            return True
        else:
            print(
                f"❌ Initialization failed: {result.get('error', 'Unknown error') if result else 'No response'}"
            )
            return False

    def initialized(self):
        """Send the initialized notification."""
        print("📡 Sending initialized notification...")
        initialized_data = {
            "jsonrpc": "2.0",
            "method": "initialized",
            "params": {},
            "id": None,  # Notification, not a request
        }

        try:
            requests.post(self.base_url, headers=self.headers, json=initialized_data)
            print("✅ Initialized notification sent!")
            return True
        except Exception as e:
            print(f"⚠️ Error sending notification: {e}")
            return False

    def call_tool(self, tool_name, arguments, request_id):
        """Call a tool on the MCP server."""
        print(f"🔨 Calling tool: {tool_name}")
        tool_data = {
            "jsonrpc": "2.0",
            "method": "call_tool",
            "params": {"name": tool_name, "arguments": arguments},
            "id": request_id,
        }

        result = self._send_request(tool_data)
        if result and "result" in result:
            print(f"✅ Tool {tool_name} executed successfully!")
            return result["result"]
        elif result and "error" in result:
            print(f"❌ Error in tool {tool_name}: {result['error']}")
            return None
        else:
            print(f"❌ Failed to run {tool_name}")
            return None


def main():
    """Main entry point to test the MCP client."""
    client = MCPClient("http://localhost:8006/mcp")

    # Step 1: Initialize the session
    if not client.initialize():
        return

    # Step 2: Send the initialized notification
    client.initialized()

    # Step 3: Test the search_brain function
    result = client.call_tool("search_brain", {"query": "architecture patterns"}, 2)
    if result:
        content = result.get("content", "")
        if len(content) > 500:
            content = content[:500] + "... (truncated)"
        print(f"Search result: {content}")

    # Step 4: Test the resolve_note function
    result = client.call_tool("resolve_note", {"name": "design"}, 3)
    if result:
        content = result.get("content", "")
        print(f"resolve_note result: {content}")

    # Step 5: Test the explore_graph function
    result = client.call_tool("explore_graph", {"note_name": "design"}, 4)
    if result:
        content = result.get("content", "")
        print(f"explore_graph result: {content}")

    # Step 6: Test the get_note_chunks function
    result = client.call_tool("get_note_chunks", {"filename": "Agent_Protocol.md"}, 5)
    if result:
        content = result.get("content", "")
        if len(content) > 500:
            content = content[:500] + "... (truncated)"
        print(f"get_note_chunks result: {content}")

    print("\n✅ All tests completed!")


if __name__ == "__main__":
    main()
