#!/usr/bin/env python3
"""
1c_logging_client.py - Context Logging and Audit

Tests logging features in the calculator server:
- ctx.info(), ctx.debug(), ctx.warning() during calculate()
- ctx.audit() creates signed audit entries

Prerequisites:
    - MACAW SDK installed (pip install macaw-client macaw-adapters)
    - Calculator server running (securemcp_calculator.py)

Run:
    # Terminal 1: Start the server
    python securemcp_calculator.py

    # Terminal 2: Run this client
    python 1c_logging_client.py

Check MACAW logs to see the logged events:
    ~/.macaw/data/tenants/<tenant>/logs/events.log
"""

from macaw_adapters.mcp import Client


def find_calculator_server(client):
    """Find the most recent calculator server."""
    agents = client.macaw_client.list_agents(agent_type="app")
    # Match exactly "securemcp-calculator:" to avoid stale "securemcp-securemcp-calculator"
    calc_servers = [
        a["agent_id"] for a in agents
        if "/app:securemcp-calculator:" in a.get("agent_id", "")
        and "/tool." not in a.get("agent_id", "")
    ]
    return calc_servers[-1] if calc_servers else None


def main():
    print("=" * 50)
    print("Example 1c: Logging & Audit Demo")
    print("=" * 50)

    client = Client("logging-test-client")
    print(f"Client: {client.client_id}")

    server = find_calculator_server(client)
    if not server:
        print("\nNo calculator server found!")
        print("Start it first: python3 securemcp_calculator.py")
        return

    print(f"Server: {server}")
    print()

    # Test calculate() - generates ctx.info(), ctx.debug(), ctx.audit()
    print("Testing calculate() - generates logging and audit:")
    print("-" * 40)

    tests = [
        ("add", 10, 5),
        ("multiply", 7, 8),
        ("subtract", 20, 7),
        ("divide", 100, 4),
    ]

    for op, a, b in tests:
        result = client.macaw_client.invoke_tool(
            "calculate",
            {"operation": op, "a": a, "b": b},
            target_agent=server
        )
        print(f"  {op}({a}, {b}) = {result}")

    print()
    print("=" * 50)
    print("Check MACAW logs at:")
    print("  ~/.macaw/data/tenants/<tenant>/logs/events.log")
    print()
    print("Look for:")
    print("  - tool_log: level=info, message='Calculating: ...'")
    print("  - tool_log: level=debug, message='Result computed: ...'")
    print("  - audit: action=calculation (signed)")
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
