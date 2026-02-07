#!/usr/bin/env python3
"""
Example 1g: MCP Roots via MAPL - CLIENT

Tests root boundaries declared by the server.

Demonstrates:
- list_roots() to discover server's allowed paths
- Access allowed within roots
- Access denied outside roots

Run 1g_roots_server.py first, then run this client.
"""

import asyncio

from macaw_adapters.mcp import Client

DEMO_DIR = "/tmp/securemcp-roots-demo"


def find_roots_server(client):
    """Find the most recent roots demo server."""
    agents = client.macaw_client.list_agents(agent_type="app")
    matching = [
        a["agent_id"] for a in agents
        if "roots-demo" in a.get("agent_id", "")
        and "/tool." not in a.get("agent_id", "")
    ]
    return matching[-1] if matching else None  # Return last (most recent)


def main():
    print("=" * 50)
    print("Example 1g: Roots Demo Client")
    print("=" * 50)

    client = Client("roots-client")
    print(f"Client: {client.client_id}")

    server = find_roots_server(client)
    if not server:
        print("\nNo roots-demo server found!")
        print("Start it first: python3 1g_roots_server.py")
        return

    print(f"Server: {server}")
    print()

    # Discover roots
    print("Discovering server roots (list_roots()):")
    print("-" * 40)

    async def show_roots():
        roots = await client.list_roots(server_name="roots-demo")
        for r in roots:
            print(f"  - {r['path']}")
        return roots

    asyncio.run(show_roots())
    print()

    # Test ALLOWED access
    print(f"Testing list_dir('{DEMO_DIR}') - ALLOWED:")
    print("-" * 40)
    result = client.macaw_client.invoke_tool("list_dir", {"path": DEMO_DIR}, target_agent=server)
    print(f"  Result: {result}")
    print()

    print(f"Testing read_file('{DEMO_DIR}/allowed.txt') - ALLOWED:")
    print("-" * 40)
    result = client.macaw_client.invoke_tool("read_file", {"path": f"{DEMO_DIR}/allowed.txt"}, target_agent=server)
    print(f"  Result: {result}")
    print()

    # Test DENIED access (should raise exception or return error)
    print("Testing list_dir('/etc') - DENIED (outside roots):")
    print("-" * 40)
    try:
        result = client.macaw_client.invoke_tool("list_dir", {"path": "/etc"}, target_agent=server)
        print(f"  Result: {result}")
    except Exception as e:
        print(f"  ✓ Access denied (as expected): {e}")
    print()

    print("Testing read_file('/etc/passwd') - DENIED:")
    print("-" * 40)
    try:
        result = client.macaw_client.invoke_tool("read_file", {"path": "/etc/passwd"}, target_agent=server)
        print(f"  Result: {result}")
    except Exception as e:
        print(f"  ✓ Access denied (as expected): {e}")
    print()

    print("=" * 50)
    print("Roots enforce filesystem boundaries via MAPL")
    print("=" * 50)


if __name__ == "__main__":
    main()
