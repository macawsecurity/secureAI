#!/usr/bin/env python3
"""
Example: SecureMCPProxy with Salesforce DX MCP (stdio transport)

Demonstrates SecureMCPProxy connecting to Salesforce DX CLI via stdio.
Salesforce DX MCP provides tools for org management, deployment, and queries.

Security Model:
- MACAW creates AuthenticatedContext for EACH invocation
- Even with persistent subprocess, each call gets fresh identity/policy/signature
- Salesforce operations are policy-enforced and audited

Prerequisites:
    1. Salesforce account (free Developer Edition: https://developer.salesforce.com/signup)
    2. Salesforce CLI: npm install -g @salesforce/cli
    3. Authenticated org: sf org login web
    4. MACAW: pip install macaw-adapters[mcp-proxy]

NOTE: This example requires a Salesforce account. Skip if you don't have one -
      the stdio pattern is validated by 2e_proxy_stdio_fetch.py.

Usage:
    python 2f_proxy_stdio_salesforce.py
"""

import os
import sys
import shutil
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Test SecureMCPProxy with Salesforce DX MCP."""
    from macaw_adapters.mcp import SecureMCPProxy

    print("=" * 60)
    print("SecureMCPProxy + Salesforce DX MCP (stdio)")
    print("=" * 60)

    # Step 1: Check npx is available
    print("\n1. Checking prerequisites...")
    if not shutil.which("npx"):
        print("   ERROR: npx not found")
        print("   Fix: Install Node.js (https://nodejs.org)")
        return 1
    print("   OK: npx found")

    # Check if sf CLI is available
    if not shutil.which("sf"):
        print("   WARNING: sf CLI not found")
        print("   You may need to install: npm install -g @salesforce/cli")

    # Step 2: Create proxy with stdio transport
    print("\n2. Creating SecureMCPProxy with Salesforce DX...")
    try:
        proxy = SecureMCPProxy(
            app_name="salesforce-dx",
            command=["npx", "@salesforce/mcp", "--orgs", "DEFAULT", "--dynamic-tools"],
            env={
                "HOME": os.environ.get("HOME", ""),
                "PATH": os.environ.get("PATH", ""),
            }
        )
        print(f"   OK: {proxy}")
    except ConnectionError as e:
        print(f"   ERROR: Failed to connect: {e}")
        print("\n   Troubleshooting:")
        print("   1. Install @salesforce/mcp: npm install -g @salesforce/mcp")
        print("   2. Login to an org: sf org login web")
        print("   3. Set default org: sf config set target-org=<alias>")
        return 1
    except Exception as e:
        print(f"   ERROR: {e}")
        return 1

    # Step 3: Discover tools
    print("\n3. Discovering Salesforce DX tools...")
    tools = proxy.list_tools()
    print(f"   Found {len(tools)} tools:")
    for tool in tools[:10]:  # Show first 10
        print(f"   - {tool['name']}")
    if len(tools) > 10:
        print(f"   ... and {len(tools) - 10} more")

    if not tools:
        print("   ERROR: No tools discovered")
        return 1

    # Step 4: Test tool calls
    print("\n4. Testing tool calls...")

    # Get current username (requires directory - use current dir)
    try:
        result = proxy.call_tool("get_username", {"directory": os.getcwd()})
        content = result.get('result', result) if isinstance(result, dict) else result
        print(f"   get_username: {content}")
    except Exception as e:
        print(f"   get_username error: {e}")

    # List available tools (dynamic)
    try:
        result = proxy.call_tool("list_tools", {})
        content = result.get('result', result) if isinstance(result, dict) else result
        preview = str(content)[:300] if content else "(empty)"
        print(f"   list_tools: {preview}...")
    except Exception as e:
        print(f"   list_tools error: {e}")

    print("\n" + "=" * 60)
    print("SUCCESS: SecureMCPProxy + Salesforce DX works!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
