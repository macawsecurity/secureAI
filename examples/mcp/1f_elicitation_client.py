#!/usr/bin/env python3
"""
Example 1f: MCP Elicitation - CLIENT

Demonstrates client.set_elicitation_handler() for server->user input.

The client registers an input handler that prompts the user when
the server's ctx.elicit() is called.

Run 1f_elicitation_server.py first, then run this client.
"""

import sys
from pathlib import Path


from macaw_adapters.mcp import Client


def find_elicitation_server(client):
    """Find the most recent elicitation demo server."""
    agents = client.macaw_client.list_agents(agent_type="app")
    matching = [
        a["agent_id"] for a in agents
        if "elicitation-demo" in a.get("agent_id", "")
        and "/tool." not in a.get("agent_id", "")
    ]
    return matching[-1] if matching else None  # Return last (most recent)


def main():
    print("=" * 50)
    print("Example 1f: Elicitation Demo Client")
    print("=" * 50)

    client = Client("elicitation-client")
    print(f"Client: {client.client_id}")

    # Register interactive input handler
    def input_handler(prompt, options, input_type, default, required, **kwargs):
        print()
        if input_type == "confirm":
            response = input(f"  {prompt} (y/n) [{default or 'n'}]: ").strip().lower()
            if not response:
                response = (default or "n").lower()
            return response in ("y", "yes")

        elif input_type == "select" and options:
            print(f"  {prompt}")
            for i, opt in enumerate(options):
                print(f"    {i+1}. {opt}")
            while True:
                try:
                    choice = input(f"  Enter number (1-{len(options)}): ").strip()
                    idx = int(choice) - 1
                    if 0 <= idx < len(options):
                        return options[idx]
                except ValueError:
                    pass
                print("  Invalid choice, try again")

        else:  # text
            response = input(f"  {prompt}: ").strip()
            return response or default

    client.set_elicitation_handler(input_handler)
    print("Elicitation handler registered (interactive)")
    print()

    server = find_elicitation_server(client)
    if not server:
        print("\nNo elicitation-demo server found!")
        print("Start it first: python3 1f_elicitation_server.py")
        return

    print(f"Server: {server}")
    print()

    # Test create_profile
    print("Testing create_profile():")
    print("-" * 40)
    result = client.macaw_client.invoke_tool(
        "create_profile",
        {},
        target_agent=server
    )
    print(f"\n  Result: {result}")
    print()

    # Test delete_item
    print("Testing delete_item():")
    print("-" * 40)
    result = client.macaw_client.invoke_tool(
        "delete_item",
        {"item_name": "important_file.txt"},
        target_agent=server
    )
    print(f"\n  Result: {result}")

    print()
    print("=" * 50)
    print("Elicitation enables human-in-the-loop workflows")
    print("=" * 50)


if __name__ == "__main__":
    main()
