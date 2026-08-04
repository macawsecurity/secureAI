"""
MACAW Adapter for Pydantic AI

Drop-in replacement for pydantic_ai.Agent. Model calls become
tool:<app>/generate and tool calls become tool:<app>/<tool_name>, so both are
governed by the MAPL policies you already write.

Usage:
    from macaw_adapters.pydantic_ai import SecureAgent
    from pydantic_ai.models.openai import OpenAIChatModel

    agent = SecureAgent(
        OpenAIChatModel("gpt-4o"),
        app_name="acme",
        tools=[query_catalog, get_lineage],
    )
    result = await agent.run("which tables contain PII?")

Multi-user:
    alice_agent = agent.bind_to_user(alice_client)

Prerequisites:
    - MACAW Client Library: https://console.macawsecurity.ai
    - pip install macaw-adapters[pydantic-ai]
"""

from macaw_adapters.pydantic_ai.agent import Agent, SecureAgent
from macaw_adapters.pydantic_ai.model import SecureModel
from macaw_adapters.pydantic_ai.toolset import SecureToolset

__all__ = [
    "SecureAgent",
    "Agent",  # drop-in alias
    "SecureModel",
    "SecureToolset",
]
