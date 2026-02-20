#!/usr/bin/env python3
"""
1a_simple_invocation.py - Simple MCP Tool Invocation

Demonstrates:
- Auto-discovering SecureMCP servers
- Invoking tools on a server
- Basic tool calls (add, subtract, multiply, divide)
- Tool with context (calculate with history)

Prerequisites:
    - MACAW SDK installed (pip install macaw-client macaw-adapters)
    - Calculator server running (securemcp_calculator.py)

Run:
    # Terminal 1: Start the server
    python securemcp_calculator.py

    # Terminal 2: Run this client
    python 1a_simple_invocation.py
"""

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


def main():
    print("=" * 50)
    print("Example 1a: Simple Tool Invocation")
    print("=" * 50)

    # Create client (auto-registers with LocalAgent)
    client = Client("example-1a")
    print(f"Client: {client.client_id}")

    # Find calculator server
    server_id = find_calculator_server(client)
    if not server_id:
        return

    print(f"Server: {server_id}")
    print()

    # Test basic tools
    print("Basic Tool Invocations:")
    print("-" * 40)

    tests = [
        ("add", {"a": 10, "b": 5}),
        ("subtract", {"a": 100, "b": 42}),
        ("multiply", {"a": 7, "b": 8}),
        ("divide", {"a": 100, "b": 4}),
    ]

    for tool_name, args in tests:
        result = client.macaw_client.invoke_tool(
            tool_name,
            args,
            target_agent=server_id
        )
        args_str = ", ".join(f"{k}={v}" for k, v in args.items())
        print(f"  {tool_name}({args_str}) = {result}")

    print()

    # Test tool with context
    print("Tool with Context (history tracking):")
    print("-" * 40)

    for op in ["add", "multiply", "subtract"]:
        result = client.macaw_client.invoke_tool(
            "calculate",
            {"operation": op, "a": 10, "b": 3},
            target_agent=server_id
        )
        print(f"  calculate({op}, 10, 3) = {result}")

    print()
    print("=" * 50)
    print("Done!")
    print("=" * 50)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err = str(e)
        print("\n" + "=" * 50)
        if "Connection refused" in err or "connect" in err.lower():
            print("ERROR: Cannot connect to MACAW")
            print("Fix: Ensure MACAW is running")
        else:
            print(f"ERROR: {e}")
        print("=" * 50)
        import sys
        sys.exit(1)
