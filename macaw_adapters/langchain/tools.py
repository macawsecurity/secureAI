"""
MACAW Tool Wrappers - LangChain tools routed through MACAW PEP.

Usage:
    from macaw_adapters.langchain.tools import SecureToolWrapper, wrap_tools

    # Wrap individual tool
    secure_tool = SecureToolWrapper(original_tool, macaw_client)

    # Wrap list of tools
    secure_tools = wrap_tools(tools, macaw_client)
"""

import logging
from typing import Any, List, Optional

from langchain_core.tools import BaseTool
from langchain_core.callbacks import CallbackManagerForToolRun, AsyncCallbackManagerForToolRun
from macaw_client import MACAWClient

logger = logging.getLogger(__name__)


class SecureToolWrapper(BaseTool):
    """
    Wrapper for LangChain tools that routes execution through MACAW PEP.

    Inherits from BaseTool to be fully compatible with LangChain's
    AgentExecutor and validation. Enforces security policies via MACAWClient.
    """

    # Pydantic fields
    original_tool: Any = None
    macaw_client: Any = None

    class Config:
        arbitrary_types_allowed = True

    def __init__(self, original_tool: Any, macaw_client: MACAWClient, **kwargs):
        """
        Initialize secure tool wrapper.

        Args:
            original_tool: LangChain BaseTool instance
            macaw_client: MACAWClient for policy enforcement
        """
        # Extract attributes from original tool for BaseTool
        super().__init__(
            name=original_tool.name,
            description=original_tool.description,
            original_tool=original_tool,
            macaw_client=macaw_client,
            **kwargs
        )

        # Copy optional attributes
        if hasattr(original_tool, 'args_schema') and original_tool.args_schema:
            self.args_schema = original_tool.args_schema
        if hasattr(original_tool, 'return_direct'):
            self.return_direct = original_tool.return_direct

    def _run(
        self,
        tool_input: str = "",
        run_manager: Optional[CallbackManagerForToolRun] = None,
        **kwargs
    ) -> str:
        """Execute tool through MACAW PEP."""
        logger.debug(f"[SecureTool] Routing {self.name} through MACAW")

        try:
            # Build parameters dict
            parameters = {"input": tool_input}

            # Invoke tool through MACAW protocol
            # Authenticated prompts are auto-created by invoke_tool() based on registry
            result = self.macaw_client.invoke_tool(
                tool_name=self.name,
                parameters=parameters,
                target_agent=self.macaw_client.agent_id
            )
            return str(result) if result is not None else ""

        except Exception as e:
            error_msg = str(e).lower()
            if any(word in error_msg for word in ['denied', 'blocked', 'policy']):
                logger.warning(f"MACAW blocked {self.name}: {e}")
                return f"Access denied by security policy: {self.name}"
            raise

    async def _arun(
        self,
        tool_input: str = "",
        run_manager: Optional[AsyncCallbackManagerForToolRun] = None,
        **kwargs
    ) -> str:
        """Async execution (delegates to sync)."""
        return self._run(tool_input, **kwargs)


def wrap_tools(tools: List[Any], macaw_client: MACAWClient) -> List[SecureToolWrapper]:
    """
    Wrap a list of LangChain tools with MACAW security.

    Args:
        tools: List of LangChain BaseTool instances
        macaw_client: MACAWClient for policy enforcement

    Returns:
        List of SecureToolWrapper instances
    """
    return [SecureToolWrapper(tool, macaw_client) for tool in tools]


def secure_tool(func=None, *, macaw_client: Optional[MACAWClient] = None):
    """
    Decorator to create a secure LangChain tool with MACAW protection.

    Usage:
        @secure_tool
        def search_database(query: str) -> str:
            '''Search the database for relevant information.'''
            return database.search(query)

        # Or with explicit client:
        @secure_tool(macaw_client=my_client)
        def my_tool(x: str) -> str:
            '''My tool description.'''
            return process(x)

    Args:
        func: The function to wrap (used when called without parentheses)
        macaw_client: Optional MACAWClient for policy enforcement

    Returns:
        A SecureToolWrapper compatible with LangChain agents
    """
    from langchain_core.tools import tool as langchain_tool
    from ._utils import get_or_create_client

    def decorator(fn):
        # Create LangChain tool from function
        lc_tool = langchain_tool(fn)

        # Get or create MACAW client
        client = macaw_client or get_or_create_client("langchain-tools")
        if client is None:
            logger.warning("Could not create MACAWClient, returning unwrapped tool")
            return lc_tool

        # Wrap with MACAW security
        return SecureToolWrapper(lc_tool, client)

    if func is not None:
        # Called without parentheses: @secure_tool
        return decorator(func)
    else:
        # Called with parentheses: @secure_tool() or @secure_tool(macaw_client=...)
        return decorator
