"""
MACAW MCP Adapter - FastMCP-compatible API with MACAW Security.

Provides the same decorator-based API as FastMCP while routing all tool
invocations through the MACAW security layer for policy enforcement,
cryptographic signing, and audit logging.

Usage:
    from macaw_adapters.mcp import SecureMCP, Context

    mcp = SecureMCP("calculator")

    @mcp.tool(description="Add two numbers")
    def add(a: float, b: float) -> float:
        return a + b

    if __name__ == "__main__":
        mcp.run()

Features:
    - FastMCP-compatible decorator API
    - Policy-enforced tool execution
    - Cryptographic audit trail
    - MCP protocol compliant

For more information: https://macawsecurity.ai
"""

__version__ = "0.2.0"

# Primary FastMCP-compatible API
from .mcp import SecureMCP, Context

# Legacy API (backwards compatibility)
from .server import Server
from .client import Client

__all__ = [
    # Primary API
    "SecureMCP",
    "Context",
    # Legacy
    "Server",
    "Client",
    "__version__"
]