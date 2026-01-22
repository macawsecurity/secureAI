"""
MACAW LangChain Adapter - Drop-in replacements for LangChain with MACAW protection.

Usage:
    # LLM providers (mirrors langchain_openai / langchain_anthropic)
    from macaw_adapters.langchain.openai import ChatOpenAI
    from macaw_adapters.langchain.anthropic import ChatAnthropic

    # Memory classes (mirrors langchain.memory)
    from macaw_adapters.langchain.memory import ConversationBufferMemory

    # Agent functions (mirrors langchain.agents)
    from macaw_adapters.langchain.agents import create_react_agent, AgentExecutor

    # Tool wrappers
    from macaw_adapters.langchain.tools import SecureToolWrapper, wrap_tools

Features:
    - Drop-in replacement for LangChain components
    - Policy-enforced tool execution
    - Secure memory with integrity verification
    - Cryptographic audit trail
"""

# Submodules (enable namespace imports)
from . import openai
from . import anthropic
from . import memory
from . import agents
from . import tools
from . import callbacks

# Convenience re-exports
from .openai import ChatOpenAI
from .anthropic import ChatAnthropic
from .memory import (
    ConversationBufferMemory,
    ConversationBufferWindowMemory,
    ConversationSummaryMemory
)
from .agents import (
    create_react_agent,
    create_openai_functions_agent,
    AgentExecutor
)
from .tools import SecureToolWrapper, wrap_tools
from .callbacks import MACAWCallbackHandler
from ._utils import cleanup_all


def cleanup():
    """Clean up all MACAW resources."""
    cleanup_all()


__all__ = [
    # Submodules
    'openai',
    'anthropic',
    'memory',
    'agents',
    'tools',
    'callbacks',

    # LLM classes
    'ChatOpenAI',
    'ChatAnthropic',

    # Memory classes
    'ConversationBufferMemory',
    'ConversationBufferWindowMemory',
    'ConversationSummaryMemory',

    # Agent functions
    'create_react_agent',
    'create_openai_functions_agent',
    'AgentExecutor',

    # Tool wrappers
    'SecureToolWrapper',
    'wrap_tools',

    # Callback handler
    'MACAWCallbackHandler',

    # Cleanup
    'cleanup'
]
