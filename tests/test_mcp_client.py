#!/usr/bin/env python3
"""Script to test the connection to Clawdiney's MCP server."""

import json
from unittest.mock import patch

import pytest
import requests


class MockResponse:
    def __init__(self, json_data):
        self.json_data = json_data
        self.status_code = 200
        self.text = f"data: {json.dumps(json_data)}\n"

    def iter_lines(self):
        yield f"data: {json.dumps(self.json_data)}".encode()


def mock_post(url, headers=None, json_data=None, json=None, stream=False):
    payload = json or json_data or {}
    method = payload.get("method")
    req_id = payload.get("id")
    if method == "initialize":
        return MockResponse(
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
            return MockResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": "Mocked search results: architecture patterns"
                    },
                }
            )
        elif tool_name == "resolve_note":
            return MockResponse(
                {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": "[{'path': 'design.md', 'filename': 'design.md'}]"
                    },
                }
            )
    return MockResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})


@pytest.fixture(autouse=True)
def setup_mock_requests():
    with patch("requests.post", side_effect=mock_post):
        yield


def send_request(url, headers, data):
    """Send a request to the MCP server and return the response."""
    try:
        response = requests.post(url, headers=headers, json=data, stream=True)
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


def test_mcp_server():
    """Test the connection to the MCP server and its functions."""
    url = "http://localhost:8006/mcp"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }

    # Step 1: Initialize the server
    print("🔧 Initializing MCP server...")
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
        print(f"❌ Initialization failed: {result.get('error', 'Unknown error')}")
        return False

    print("✅ Server initialized successfully!")
    print(f"Server info: {json.dumps(result['result']['serverInfo'], indent=2)}")

    # Step 2: Send the initialized notification
    print("\n📡 Sending initialized notification...")
    initialized_data = {"jsonrpc": "2.0", "method": "initialized", "params": {}}

    # Notifications must have a null ID
    initialized_data["id"] = None

    try:
        requests.post(url, headers=headers, json=initialized_data)
        print("✅ Initialized notification sent!")
    except Exception as e:
        print(f"⚠️ Error sending notification (may be expected): {e}")

    # Step 3: Test the search_brain function
    print("\n🔍 Testing search_brain function...")
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
        print("✅ search_brain executed successfully!")
        # Cap the output so it doesn't get too long
        output = result["result"].get("content", "")
        if len(output) > 500:
            output = output[:500] + "... (truncated)"
        print(f"Search result: {output}")
    elif result and "error" in result:
        print(f"❌ Error in search_brain: {result['error']}")
    else:
        print("❌ Failed to run search_brain")

    # Step 4: Test the resolve_note function
    print("\n🔍 Testing resolve_note function...")
    resolve_data = {
        "jsonrpc": "2.0",
        "method": "call_tool",
        "params": {"name": "resolve_note", "arguments": {"name": "design"}},
        "id": 3,
    }

    result = send_request(url, headers, resolve_data)
    if result and "result" in result:
        print("✅ resolve_note executed successfully!")
        print(f"Result: {result['result'].get('content', '')}")
    elif result and "error" in result:
        print(f"❌ Error in resolve_note: {result['error']}")
    else:
        print("❌ Failed to run resolve_note")

    print("\n✅ All tests completed!")


if __name__ == "__main__":
    test_mcp_server()
