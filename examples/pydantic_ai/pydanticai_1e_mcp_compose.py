"""
Local tools and an MCP server in one agent.

A Pydantic AI agent can mix tools it owns with tools reached over MCP. Both are
governed, but at different boundaries:

    local functions   registered with MACAW and dispatched by it
                      -> tool:pydantic-agent/<name>

    MCP tools         authorized here under the caller's identity, then executed
                      by the server, which SecureMCP governs on its own side
                      -> tool:pydantic-agent/<name>   (this agent)
                      -> tool:securemcp-calculator/<name>  (the server)

The agent-side check is the one that carries the user's identity, because an MCP
connection has none of its own.

This example runs examples/mcp/securemcp_calculator.py as a subprocess over
stdio, the same way examples/mcp/3a_native_mcp_client.py does.

Prerequisites:
    export OPENAI_API_KEY=sk-...
    MACAW LocalAgent running
    Workspace policy allowing tool:pydantic-agent/*

Run:
    python pydanticai_1e_mcp_compose.py
"""

import asyncio
import os
import sys
from pathlib import Path

from pydantic_ai.mcp import MCPToolset, StdioTransport
from pydantic_ai.models.openai import OpenAIChatModel

from macaw_adapters.pydantic_ai import SecureAgent

APP_NAME = "pydantic-agent"
GENERATE = f"tool:{APP_NAME}/generate"

CALCULATOR = Path(__file__).resolve().parents[1] / "mcp" / "securemcp_calculator.py"


def describe_result(value: str) -> str:
    """Write a one-line description of a calculation result."""
    return f"result recorded: {value}"


async def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY first:")
        print("  export OPENAI_API_KEY=sk-...")
        return 1

    if not CALCULATOR.exists():
        print(f"Calculator server not found: {CALCULATOR}")
        return 1

    # env is passed through so the server subprocess can import macaw_adapters
    # when running from a source checkout rather than an installed package.
    calculator = MCPToolset(
        StdioTransport(
            command=sys.executable,
            args=[str(CALCULATOR), "stdio"],
            env=dict(os.environ),
        )
    )

    agent = SecureAgent(
        OpenAIChatModel("gpt-4o-mini"),
        app_name=APP_NAME,
        tools=[describe_result],          # owned: MACAW dispatches these
        toolsets=[calculator],            # MCP: MACAW authorizes, server executes
        intent_policy={"resources": [GENERATE, f"tool:{APP_NAME}/*"]},
    )
    print(f"Registered: {agent._macaw.server_id}")
    print(f"Local tools: describe_result")
    print(f"MCP server : {CALCULATOR.name}")

    result = await agent.run(
        "Add 17 and 25 using the calculator, then describe the result."
    )
    print(f"\n{result.output}")
    print("\nBoth tools were invoked through MACAW under this agent's identity.")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
