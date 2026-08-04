"""
Pydantic AI drop-in: model and tool calls governed by MACAW.

The simplest integration path - replace the Agent import and add app_name.

    # BEFORE
    from pydantic_ai import Agent
    agent = Agent(OpenAIChatModel("gpt-4o-mini"), tools=[query_catalog])

    # AFTER
    from macaw_adapters.pydantic_ai import SecureAgent
    agent = SecureAgent(OpenAIChatModel("gpt-4o-mini"), app_name="catalog-agent",
                        tools=[query_catalog])

Every model call becomes tool:catalog-agent/generate and every tool call becomes
tool:catalog-agent/<tool_name>, so both are governed by MAPL policy.

Prerequisites:
    export OPENAI_API_KEY=sk-...
    MACAW LocalAgent running

Run:
    python pydanticai_1a_dropin_simple.py
"""

import os
import sys

from pydantic_ai.models.openai import OpenAIChatModel

from macaw_adapters.pydantic_ai import SecureAgent

APP_NAME = "pydantic-agent"
GENERATE = f"tool:{APP_NAME}/generate"


def query_catalog(table: str, limit: int = 10) -> str:
    """Query the data catalog for rows from a table."""
    print(f"    [tool] query_catalog(table={table!r}, limit={limit})")
    return f"{limit} rows from {table}"


def export_dataset(table: str) -> str:
    """Export a full dataset to external storage."""
    print(f"    [tool] export_dataset(table={table!r})")
    return f"exported {table}"


def main() -> int:
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY first:")
        print("  export OPENAI_API_KEY=sk-...")
        return 1

    # Policy: gpt-4o-mini only, and the agent may query but not export.
    agent = SecureAgent(
        OpenAIChatModel("gpt-4o-mini"),
        app_name=APP_NAME,
        tools=[query_catalog, export_dataset],
        intent_policy={
            "resources": [GENERATE, f"tool:{APP_NAME}/query_catalog"],
            "denied_resources": [f"tool:{APP_NAME}/export_dataset"],
            "constraints": {
                "parameters": {
                    GENERATE: {
                        "model": ["gpt-4o-mini"],
                        "max_tokens": {"max": 500},
                    }
                }
            },
        },
    )

    print(f"Registered: {agent._macaw.server_id}")
    print(f"Policy:     gpt-4o-mini only; query_catalog allowed, export_dataset denied")

    print("\n--- Allowed: query the catalog ---")
    result = agent.run_sync("Use query_catalog on the customers table with limit 3.")
    print(f"  {result.output}")

    print("\n--- Denied: export a dataset ---")
    result = agent.run_sync("Export the customers table using export_dataset.")
    print(f"  {result.output}")
    print("\n  The tool never ran. MACAW denied it and the model adapted.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
