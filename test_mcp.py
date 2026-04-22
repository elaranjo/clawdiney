from mcp.server.fastmcp import FastMCP

# Initialize FastMCP Server
mcp = FastMCP("TestServer", port=8006)


@mcp.tool()
def hello_world() -> str:
    """A simple test tool"""
    return "Hello, World!"


if __name__ == "__main__":
    print("Starting test server on port 8006...")
    mcp.run()
