#!/usr/bin/env python3
"""
3a_native_mcp_client.py - A vanilla MCP client talking to SecureMCP

This client knows NOTHING about MACAW. It has no macaw imports, no agent
registration, no target_agent, no LocalAgent. It is the same code you would write
against any MCP server, and it is what Claude Desktop / Cursor do internally.

It still gets full MACAW enforcement, because the server's run(transport="stdio")
turns every JSON-RPC call into the same invoke_tool() a MACAW client would make:

    this client --JSON-RPC--> calculator's MCP endpoint
                                  |
                                  +--> invoke_tool --> LocalAgent --> PEP --> add()
                                            policy . signing . audit

Prerequisites:
    - MACAW LocalAgent running
    - pip install mcp

Run:
    python 3a_native_mcp_client.py

    (this spawns securemcp_calculator.py itself - no separate terminal needed)
"""

import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

SERVER = Path(__file__).parent / "securemcp_calculator.py"


async def main() -> int:
    print("=" * 60)
    print("Vanilla MCP client -> SecureMCP calculator")
    print("=" * 60)

    params = StdioServerParameters(
        command=sys.executable,
        args=[str(SERVER), "stdio"],
    )

    async with stdio_client(params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:

            # 1. Handshake
            init = await session.initialize()
            print(f"\nConnected to: {init.serverInfo.name} v{init.serverInfo.version}")
            print(f"Protocol: {init.protocolVersion}")

            # 2. Discovery - comes straight off the MACAW tool registry
            listed = await session.list_tools()
            print(f"\nDiscovered {len(listed.tools)} tools:")
            for tool in listed.tools:
                required = tool.inputSchema.get("required", [])
                print(f"  - {tool.name}({', '.join(required)}): {tool.description}")

            # 3. Call tools - each one goes through the MACAW PEP
            print("\nCalls (each policy-checked, signed, audited):")
            for tool_name, args in [
                ("add", {"a": 10, "b": 5}),
                ("subtract", {"a": 100, "b": 42}),
                ("multiply", {"a": 7, "b": 8}),
                ("divide", {"a": 100, "b": 4}),
            ]:
                result = await session.call_tool(tool_name, args)
                shown = ", ".join(f"{k}={v}" for k, v in args.items())
                print(f"  {tool_name}({shown}) = {result.content[0].text}")

            # 4. A tool that uses Context (vault + audit) - works unchanged
            result = await session.call_tool(
                "calculate", {"operation": "add", "a": 10, "b": 3}
            )
            print(f"  calculate(add, 10, 3) = {result.content[0].text}")

    print("\n" + "=" * 60)
    print("Done - and this file contains no MACAW code at all.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except Exception as e:
        print(f"\nERROR: {e}")
        print("\nCheck that the MACAW LocalAgent is running.")
        sys.exit(1)
