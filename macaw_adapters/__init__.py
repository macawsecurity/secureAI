"""
MACAW Adapters - Secure AI Adapters for Enterprise

Security adapters for popular AI frameworks including OpenAI, Anthropic,
LangChain, and MCP (Model Context Protocol).

Usage:
    from macaw_adapters.openai import SecureOpenAI
    from macaw_adapters.anthropic import SecureAnthropic
    from macaw_adapters.langchain.agents import create_react_agent, AgentExecutor
    from macaw_adapters.mcp import SecureMCP

Prerequisites:
    - MACAW Client Library: Download from https://macawsecurity.ai
    - Free Account: Create at https://console.macawsecurity.ai

For more information, visit: https://macawsecurity.ai
"""

__version__ = "0.5.25"
__author__ = "MACAW Security"
__license__ = "Apache-2.0"

# Lazy imports - only load adapters when explicitly imported
# This allows using one adapter without installing dependencies for others
# e.g., `from macaw_adapters.mcp import SecureMCP` works without openai installed

__all__ = [
    "openai",
    "anthropic",
    "langchain",
    "mcp",
    "__version__",
]


def __getattr__(name):
    """Lazy import adapters only when accessed."""
    if name == "openai":
        from macaw_adapters import openai
        return openai
    elif name == "anthropic":
        from macaw_adapters import anthropic
        return anthropic
    elif name == "langchain":
        from macaw_adapters import langchain
        return langchain
    elif name == "mcp":
        from macaw_adapters import mcp
        return mcp
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
