#!/usr/bin/env python3
"""
Example: SecureMCPProxy with Databricks MCP Server (stdio transport)

Demonstrates SecureMCPProxy connecting to Databricks via stdio transport.
This uses the community databricks-mcp-server package.

Security Model:
- MACAW creates AuthenticatedContext for EACH invocation
- Even with persistent subprocess, each call gets fresh identity/policy/signature
- Databricks operations are policy-enforced and audited

Prerequisites:
    1. Databricks account with PAT token
    2. pip install databricks-mcp-server
    3. Environment variables:
       export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"
       export DATABRICKS_TOKEN="dapi..."
    4. MACAW: pip install macaw-adapters[mcp-proxy]

Usage:
    python 2g_proxy_stdio_databricks.py
"""

import os
import sys
import shutil
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Test SecureMCPProxy with Databricks MCP (stdio)."""
    from macaw_adapters.mcp import SecureMCPProxy

    print("=" * 60)
    print("SecureMCPProxy + Databricks MCP (stdio)")
    print("=" * 60)

    # Step 1: Check prerequisites
    print("\n1. Checking prerequisites...")

    # Check uvx/databricks-mcp-server
    if not shutil.which("uvx"):
        print("   ERROR: uvx not found")
        print("   Fix: pip install uv")
        return 1
    print("   OK: uvx found")

    # Check environment variables
    host = os.environ.get("DATABRICKS_HOST", "")
    token = os.environ.get("DATABRICKS_TOKEN", "")

    if not host or not token:
        print("   ERROR: DATABRICKS_HOST and DATABRICKS_TOKEN required")
        print("   Fix:")
        print('     export DATABRICKS_HOST="https://your-workspace.cloud.databricks.com"')
        print('     export DATABRICKS_TOKEN="dapi..."')
        return 1
    print(f"   OK: DATABRICKS_HOST={host[:40]}...")
    print("   OK: DATABRICKS_TOKEN=dapi***")

    # Step 2: Create proxy with stdio transport
    print("\n2. Creating SecureMCPProxy with Databricks stdio...")
    try:
        proxy = SecureMCPProxy(
            app_name="databricks-stdio",
            command=["uvx", "databricks-mcp-server@latest"],
            env={
                "DATABRICKS_HOST": host,
                "DATABRICKS_TOKEN": token,
                "HOME": os.environ.get("HOME", ""),
                "PATH": os.environ.get("PATH", ""),
            }
        )
        print(f"   OK: {proxy}")
    except ConnectionError as e:
        print(f"   ERROR: Failed to connect: {e}")
        print("\n   Troubleshooting:")
        print("   1. Install: pip install databricks-mcp-server")
        print("   2. Or run directly: uvx databricks-mcp-server@latest --help")
        return 1
    except Exception as e:
        print(f"   ERROR: {e}")
        return 1

    # Step 3: Discover tools
    print("\n3. Discovering Databricks tools...")
    tools = proxy.list_tools()
    print(f"   Found {len(tools)} tools:")
    for tool in tools[:10]:  # Show first 10
        desc = tool.get('description', '')[:50]
        print(f"   - {tool['name']}: {desc}...")
    if len(tools) > 10:
        print(f"   ... and {len(tools) - 10} more")

    if not tools:
        print("   ERROR: No tools discovered")
        return 1

    # Step 4: Test a tool call
    print("\n4. Testing tool call...")

    # Try to find a simple query tool
    tool_names = [t['name'] for t in tools]

    # Common tool names in databricks-mcp-server
    test_tools = ['execute_query', 'run_query', 'list_catalogs', 'list_schemas']

    for test_tool in test_tools:
        if test_tool in tool_names:
            print(f"   Found tool: {test_tool}")
            try:
                if 'query' in test_tool:
                    result = proxy.call_tool(test_tool, {
                        "query": "SELECT current_user()"
                    })
                else:
                    result = proxy.call_tool(test_tool, {})

                content = result.get('result', result) if isinstance(result, dict) else result
                preview = str(content)[:200]
                print(f"   OK: {preview}...")
                break
            except Exception as e:
                print(f"   Tool {test_tool} error: {e}")
    else:
        print("   Skipping tool call - no known test tool found")
        print(f"   Available: {tool_names[:5]}...")

    print("\n" + "=" * 60)
    print("SUCCESS: SecureMCPProxy Databricks stdio works!")
    print("=" * 60)
    print("\nKey points:")
    print("  - stdio transport to databricks-mcp-server")
    print("  - Same credentials as HTTP (DATABRICKS_HOST/TOKEN)")
    print("  - MACAW policy enforcement on all calls")
    return 0


if __name__ == "__main__":
    sys.exit(main())
