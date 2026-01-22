#!/usr/bin/env python3
"""
Example 1b: Discovery and Resources

Demonstrates:
- list_tools() - discover available tools
- list_resources() - discover available resources
- list_prompts() - discover available prompts
- get_resource() - read a resource
- get_prompt() - get a prompt template
- Filtering by server name

Run securemcp_calculator.py first, then run this.
"""

import sys
import asyncio
from pathlib import Path


from macaw_adapters.mcp import Client


def find_calculator_server(client):
    """Find the most recent securemcp-calculator server."""
    agents = client.macaw_client.list_agents(agent_type="app")
    # Match exactly "/app:securemcp-calculator:" to avoid stale registrations
    calc_servers = [
        a for a in agents
        if "/app:securemcp-calculator:" in a.get("agent_id", "")
        and "/tool." not in a.get("agent_id", "")
    ]

    if not calc_servers:
        print("No calculator server found!")
        print("\nStart the calculator server first:")
        print("  python3 securemcp_calculator.py")
        return None

    return calc_servers[-1]["agent_id"]


async def main():
    print("=" * 50)
    print("Example 1b: Discovery and Resources")
    print("=" * 50)

    # Create client
    client = Client("example-1b")
    print(f"Client: {client.client_id}")

    # Find calculator server
    server_id = find_calculator_server(client)
    if not server_id:
        return

    print(f"Server: {server_id}")
    print()

    # Filter for calculator server only
    server_filter = "securemcp-calculator"

    # 1. Discover tools
    print(f"list_tools('{server_filter}'):")
    print("-" * 40)
    tools = await client.list_tools(server_name=server_filter)
    for t in tools:
        print(f"  - {t['name']}")
    print()

    # 2. Discover resources
    print(f"list_resources('{server_filter}'):")
    print("-" * 40)
    resources = await client.list_resources(server_name=server_filter)
    for r in resources:
        print(f"  - {r['uri']}")
    print()

    # 3. Discover prompts
    print(f"list_prompts('{server_filter}'):")
    print("-" * 40)
    prompts = await client.list_prompts(server_name=server_filter)
    for p in prompts:
        print(f"  - {p['name']}")
    print()

    # Set default server for convenience
    client.set_default_server(server_id)

    # 4. Invoke a tool to create some history
    print("Creating history with calculate():")
    print("-" * 40)
    for op, a, b in [("add", 5, 3), ("multiply", 4, 7)]:
        result = client.macaw_client.invoke_tool(
            "calculate",
            {"operation": op, "a": a, "b": b},
            target_agent=server_id
        )
        print(f"  calculate({op}, {a}, {b}) = {result['result']}")
    print()

    # 5. Read a resource
    print("get_resource('calc://history'):")
    print("-" * 40)
    history = await client.get_resource("calc://history")
    print(f"  History count: {history.get('count', 0)}")
    for entry in history.get("history", [])[-3:]:  # Last 3 entries
        print(f"    - {entry}")
    print()

    # 6. Get a prompt
    print("get_prompt('calculation_prompt', {numbers: '1,2,3'}):")
    print("-" * 40)
    prompt = await client.get_prompt("calculation_prompt", {"numbers": "1,2,3"})
    print(f"  {prompt}")
    print()

    print("=" * 50)
    print("Done!")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
