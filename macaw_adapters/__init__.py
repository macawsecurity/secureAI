"""
MACAW Adapters - Secure AI Adapters for Enterprise

Security adapters for popular AI frameworks including OpenAI, Anthropic,
LangChain, LiteLLM (100+ providers), and MCP (Model Context Protocol).

Usage:
    from macaw_adapters.openai import SecureOpenAI
    from macaw_adapters.anthropic import SecureAnthropic
    from macaw_adapters.langchain.agents import create_react_agent, AgentExecutor
    from macaw_adapters.mcp import SecureMCP

    # LiteLLM - drop-in replacement supporting 100+ providers
    from macaw_adapters import litellm
    response = litellm.completion(model="groq/llama3-70b", messages=[...])

Prerequisites:
    - MACAW Client Library: Download from https://macawsecurity.ai
    - Free Account: Create at https://console.macawsecurity.ai

For more information, visit: https://macawsecurity.ai
"""

__version__ = "0.9.9.6"
__author__ = "MACAW Security"
__license__ = "Apache-2.0"

# Lazy imports - only load adapters when explicitly imported
# This allows using one adapter without installing dependencies for others
# e.g., `from macaw_adapters.mcp import SecureMCP` works without openai installed

__all__ = [
    "openai",
    "anthropic",
    "langchain",
    "litellm",
    "mcp",
    "pydantic_ai",
    "__version__",
]


def __getattr__(name):
    """
    Lazy import adapters only when accessed.

    Imported by full module path: an adapter shares its name with the package it
    wraps (openai, mcp, pydantic_ai, ...), and `from macaw_adapters import <name>`
    falls back to this function for those, which recurses.
    """
    if name in ("openai", "anthropic", "langchain", "litellm", "mcp", "pydantic_ai"):
        import importlib

        return importlib.import_module(f"macaw_adapters.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
