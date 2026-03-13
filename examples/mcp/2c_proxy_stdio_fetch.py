#!/usr/bin/env python3
"""
Example: SecureMCPProxy with mcp-server-fetch (stdio transport)

Demonstrates SecureMCPProxy connecting to a standard MCP server via stdio.
This validates the stdio transport with a simple, credential-free MCP server.

Security Model:
- MACAW creates AuthenticatedContext for EACH invocation
- Even with persistent subprocess, each call gets fresh identity/policy/signature
- Solves the "shared context" problem in standard MCP

Prerequisites:
    pip install mcp-server-fetch
    pip install macaw-adapters[mcp-proxy]

Usage:
    python 2e_proxy_stdio_fetch.py
"""

import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Test SecureMCPProxy with mcp-server-fetch."""
    from macaw_adapters.mcp import SecureMCPProxy

    print("=" * 60)
    print("SecureMCPProxy + mcp-server-fetch (stdio)")
    print("=" * 60)

    # Step 1: Check mcp-server-fetch is installed
    print("\n1. Checking mcp-server-fetch installation...")
    try:
        import mcp_server_fetch
        print("   OK: mcp-server-fetch is installed")
    except ImportError:
        print("   ERROR: mcp-server-fetch not installed")
        print("   Fix: pip install mcp-server-fetch")
        return 1

    # Step 2: Create proxy with stdio transport
    print("\n2. Creating SecureMCPProxy with stdio transport...")
    try:
        proxy = SecureMCPProxy(
            app_name="fetch-stdio-test",
            command=["python", "-m", "mcp_server_fetch"],
        )
        print(f"   OK: {proxy}")
    except Exception as e:
        print(f"   ERROR: {e}")
        return 1

    # Step 3: Discover tools
    print("\n3. Discovering tools...")
    tools = proxy.list_tools()
    print(f"   Found {len(tools)} tools:")
    for tool in tools:
        desc = tool.get('description', '')[:50]
        print(f"   - {tool['name']}: {desc}...")

    if not tools:
        print("   ERROR: No tools discovered")
        return 1

    # Step 4: Call fetch tool
    print("\n4. Calling fetch tool (https://httpbin.org/html)...")
    try:
        result = proxy.call_tool("fetch", {"url": "https://httpbin.org/html"})
        if result:
            content = result.get('result', result) if isinstance(result, dict) else result
            preview = str(content)[:200].replace('\n', ' ')
            print(f"   OK: {preview}...")
        else:
            print("   OK: (empty result)")
    except Exception as e:
        print(f"   ERROR: {e}")
        return 1

    print("\n" + "=" * 60)
    print("SUCCESS: SecureMCPProxy stdio transport works!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
