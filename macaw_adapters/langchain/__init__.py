"""
MACAW LangChain Adapter - Drop-in replacements for LangChain with MACAW protection.

Usage:
    # LLM providers (mirrors langchain_openai / langchain_anthropic)
    from macaw_adapters.langchain import ChatOpenAI, ChatAnthropic

    # Or use explicit "Secure" names
    from macaw_adapters.langchain import SecureChatOpenAI, SecureChatAnthropic

    # Memory classes (mirrors langchain.memory)
    from macaw_adapters.langchain.memory import ConversationBufferMemory

    # Agent functions (mirrors langchain.agents)
    from macaw_adapters.langchain.agents import create_react_agent, AgentExecutor

    # Tool wrappers
    from macaw_adapters.langchain.tools import SecureToolWrapper, wrap_tools

Features:
    - Drop-in replacement for LangChain components
    - Policy-enforced LLM calls via SecureOpenAI/SecureAnthropic internally
    - Policy-enforced tool execution via invoke_tool
    - Per-user identity propagation via bind_to_user
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

# Explicit "Secure" aliases (same classes, clearer naming)
SecureChatOpenAI = ChatOpenAI
SecureChatAnthropic = ChatAnthropic
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
from .tools import SecureToolWrapper, wrap_tools, secure_tool
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

    # LLM classes (drop-in names)
    'ChatOpenAI',
    'ChatAnthropic',

    # LLM classes (explicit Secure names - same classes)
    'SecureChatOpenAI',
    'SecureChatAnthropic',

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
    'secure_tool',

    # Callback handler
    'MACAWCallbackHandler',

    # Cleanup
    'cleanup'
]
