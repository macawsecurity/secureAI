#!/usr/bin/env python3
"""
3b_native_mcp_proxy.py - A vanilla MCP client talking THROUGH SecureMCPProxy

The "we don't have the code" case. mcp_server_fetch is a third-party MCP server
we don't control. Put it behind SecureMCPProxy and every call is policy-checked,
signed, and audited - and the client can't tell the difference:

    this client --JSON-RPC--> proxy.run()
                                  |
                                  +--> invoke_tool --> LocalAgent --> PEP
                                                                       |
                                                    proxy handler --> mcp_server_fetch
                                                        (stdio)             |
                                                                        the web

This is the drop-in story: in a Claude Desktop config you point at this proxy
instead of at mcp_server_fetch, and nothing else changes.

Prerequisites:
    - MACAW LocalAgent running
    - pip install mcp mcp-server-fetch
    - Policy allowing: tool:fetch-test/fetch

Run:
    python 3b_native_mcp_proxy.py

    (this spawns the proxy itself - no separate terminal needed)
"""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

APP_NAME = "fetch-test"

# The proxy process this client spawns. Two lines of real code:
#     SecureMCPProxy(app_name=..., command=[...]).run()
# In a Claude Desktop config, this is what "command"/"args" would point at.
RUNNER = f'''
import sys
from macaw_adapters.mcp import SecureMCPProxy
SecureMCPProxy(
    app_name="{APP_NAME}",
    command=[sys.executable, "-m", "mcp_server_fetch"],
).run(transport="stdio")
'''


async def main() -> int:
    print("=" * 60)
    print("Vanilla MCP client -> SecureMCPProxy -> mcp_server_fetch")
    print("=" * 60)

    params = StdioServerParameters(command=sys.executable, args=["-c", RUNNER])

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:

            init = await session.initialize()
            print(f"\nConnected to: {init.serverInfo.name}")

            # Discovery passes upstream's schema through untouched - the proxy
            # never had to know what a "fetch" tool looks like.
            listed = await session.list_tools()
            print(f"\nDiscovered {len(listed.tools)} tools (schemas from upstream):")
            for tool in listed.tools:
                props = list((tool.inputSchema or {}).get("properties", {}).keys())
                print(f"  - {tool.name}({', '.join(props)})")
                print(f"    {(tool.description or '')[:70]}...")

            print("\nCall (policy-checked, signed, audited, then forwarded upstream):")
            print("-" * 60)
            result = await session.call_tool("fetch", {"url": "https://example.com"})
            preview = result.content[0].text[:180].replace("\n", " ")
            print(f"  fetch(https://example.com) -> {preview}...")

    print("\n" + "=" * 60)
    print("Done - upstream is untouched, this client has no MACAW code,")
    print("and MACAW enforced every call in between.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        import mcp_server_fetch  # noqa: F401
    except ImportError:
        print("ERROR: mcp-server-fetch not installed")
        print("Fix: pip install mcp-server-fetch")
        sys.exit(1)

    try:
        sys.exit(asyncio.run(main()))
    except Exception as e:
        print(f"\nERROR: {e}")
        print("\nCheck that the MACAW LocalAgent is running, and that policy")
        print(f"allows: tool:{APP_NAME}/fetch")
        sys.exit(1)
