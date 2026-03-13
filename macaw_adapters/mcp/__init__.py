"""
MACAW MCP Adapter - FastMCP-compatible API with MACAW Security.

Two main components:
1. SecureMCP - For MCP servers YOU write (wrap your tools with MACAW security)
2. SecureMCPProxy - For MCP servers you DON'T control (inline gateway to external servers)

Usage - SecureMCP (your servers):
    from macaw_adapters.mcp import SecureMCP, Context

    mcp = SecureMCP("calculator")

    @mcp.tool(description="Add two numbers")
    def add(a: float, b: float) -> float:
        return a + b

    mcp.run()

Usage - SecureMCPProxy (external servers):
    from macaw_adapters.mcp import SecureMCPProxy

    # Connect to external MCP server (Salesforce, Google, etc.)
    proxy = SecureMCPProxy(
        app_name="salesforce-mcp",
        upstream_url="https://mcp.salesforce.com",
        upstream_auth={"type": "bearer", "token": SF_TOKEN}
    )

    # Call tools - MACAW security applied
    result = proxy.call_tool("query_accounts", {"limit": 10})

Features:
    - FastMCP-compatible decorator API (SecureMCP)
    - Inline gateway for external MCP servers (SecureMCPProxy)
    - Policy-enforced tool execution
    - Cryptographic audit trail
    - Multi-user identity via bind_to_user()

For more information: https://macawsecurity.ai
"""

__version__ = "0.8.8"

# Primary FastMCP-compatible API (your MCP servers)
from .mcp import SecureMCP, Context

# Inline Gateway for external MCP servers
from .proxy import SecureMCPProxy, BoundMCPProxy

# Legacy API (backwards compatibility)
from .server import Server
from .client import Client

__all__ = [
    # Your MCP servers
    "SecureMCP",
    "Context",
    # External MCP servers (inline gateway)
    "SecureMCPProxy",
    "BoundMCPProxy",
    # Legacy
    "Server",
    "Client",
    "__version__"
]