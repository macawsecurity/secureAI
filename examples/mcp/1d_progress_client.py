#!/usr/bin/env python3
"""
1d_progress_client.py - Progress Reporting

Tests progress reporting in the calculator server:
- batch_calculate() reports progress via ctx.report_progress()
- Progress events are emitted to MACAW audit system

Prerequisites:
    - MACAW SDK installed (pip install macaw-client macaw-adapters)
    - Calculator server running (securemcp_calculator.py)

Run:
    # Terminal 1: Start the server
    python securemcp_calculator.py

    # Terminal 2: Run this client
    python 1d_progress_client.py
"""

from macaw_adapters.mcp import Client


def find_calculator_server(client):
    """Find the most recent calculator server."""
    agents = client.macaw_client.list_agents(agent_type="app")
    # Match exactly "/app:securemcp-calculator:" to avoid stale registrations
    calc_servers = [
        a["agent_id"] for a in agents
        if "/app:securemcp-calculator:" in a.get("agent_id", "")
        and "/tool." not in a.get("agent_id", "")
    ]
    return calc_servers[-1] if calc_servers else None


def main():
    print("=" * 50)
    print("Example 1d: Progress Reporting Demo")
    print("=" * 50)

    client = Client("progress-test-client")
    print(f"Client: {client.client_id}")

    server = find_calculator_server(client)
    if not server:
        print("\nNo calculator server found!")
        print("Start it first: python3 securemcp_calculator.py")
        return

    print(f"Server: {server}")
    print()

    # Test batch_calculate() - generates progress events
    print("Testing batch_calculate() - generates progress events:")
    print("-" * 40)

    calculations = [
        {"op": "add", "a": 1, "b": 2},
        {"op": "multiply", "a": 3, "b": 4},
        {"op": "subtract", "a": 10, "b": 3},
        {"op": "divide", "a": 100, "b": 5},
        {"op": "add", "a": 50, "b": 50},
    ]

    print(f"  Sending batch of {len(calculations)} calculations...")
    result = client.macaw_client.invoke_tool(
        "batch_calculate",
        {"calculations": calculations},
        target_agent=server
    )

    print(f"  Batch result: {result['count']} calculations")
    for r in result.get("results", []):
        print(f"    {r['expression']} = {r.get('result', r.get('error'))}")

    print()
    print("=" * 50)
    print("Check MACAW logs for progress events:")
    print("  - Progress 0%: 'Processing 5 calculations'")
    print("  - Progress 20%: 'Calculating 1/5: ...'")
    print("  - Progress 40%: 'Calculating 2/5: ...'")
    print("  - ...")
    print("  - Progress 100%: 'Batch complete'")
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
