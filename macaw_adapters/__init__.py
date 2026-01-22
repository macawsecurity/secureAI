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

__version__ = "0.5.22"
__author__ = "MACAW Security"
__license__ = "Apache-2.0"

from macaw_adapters import openai
from macaw_adapters import anthropic
from macaw_adapters import langchain
from macaw_adapters import mcp

__all__ = [
    "openai",
    "anthropic",
    "langchain",
    "mcp",
    "__version__",
]
