"""
MACAW Callback Handler - MACAW-integrated LangChain callbacks.

Usage:
    from macaw_adapters.langchain.callbacks import MACAWCallbackHandler

    # Simple usage with MACAWClient
    handler = MACAWCallbackHandler.from_client(macaw_client)
    chain = LLMChain(llm=llm, callbacks=[handler])

    # Or with the drop-in ChatOpenAI
    from macaw_adapters.langchain import ChatOpenAI, MACAWCallbackHandler

    llm = ChatOpenAI(model="gpt-4")
    handler = MACAWCallbackHandler.from_client(llm._macaw)
"""

import logging
from typing import Any, Dict, List, Optional, Union
from uuid import UUID

from macaw_client import MACAWClient
from ._utils import get_or_create_client

logger = logging.getLogger(__name__)

try:
    from langchain_core.callbacks import BaseCallbackHandler
    LANGCHAIN_AVAILABLE = True
except ImportError:
    try:
        from langchain.callbacks.base import BaseCallbackHandler
        LANGCHAIN_AVAILABLE = True
    except ImportError:
        class BaseCallbackHandler:
            pass
        LANGCHAIN_AVAILABLE = False


class MACAWCallbackHandler(BaseCallbackHandler):
    """
    LangChain callback handler that logs all events through MACAW.

    This provides audit logging for:
    - LLM invocations (on_llm_start, on_llm_end, on_llm_error)
    - Tool executions (on_tool_start, on_tool_end, on_tool_error)
    - Chain executions (on_chain_start, on_chain_end, on_chain_error)

    All events are logged via MACAWClient.log_event() for signed audit trails.
    """

    def __init__(self, macaw_client: MACAWClient):
        """
        Initialize with a MACAWClient.

        Args:
            macaw_client: MACAWClient instance for logging events
        """
        if not LANGCHAIN_AVAILABLE:
            raise ImportError("LangChain must be installed to use MACAWCallbackHandler")

        super().__init__()
        self._macaw = macaw_client

    @classmethod
    def from_client(cls, macaw_client: MACAWClient) -> 'MACAWCallbackHandler':
        """Create handler from existing MACAWClient."""
        return cls(macaw_client)

    @classmethod
    def create(cls, app_name: str = "langchain-callbacks") -> 'MACAWCallbackHandler':
        """Create handler with a new MACAWClient."""
        client = get_or_create_client(app_name)
        if not client:
            raise RuntimeError("Failed to create MACAWClient")
        return cls(client)

    # LLM Callbacks

    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any
    ) -> None:
        """Log LLM invocation start."""
        self._macaw.log_event(
            event_type="llm_start",
            action="start",
            target=f"llm:{serialized.get('name', 'unknown')}",
            metadata={
                "run_id": str(run_id),
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
                "model": serialized.get("name"),
                "prompt_count": len(prompts),
                "total_prompt_length": sum(len(p) for p in prompts)
            }
        )

    def on_llm_end(
        self,
        response: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any
    ) -> None:
        """Log LLM invocation completion."""
        self._macaw.log_event(
            event_type="llm_end",
            action="complete",
            target="llm",
            metadata={
                "run_id": str(run_id),
                "parent_run_id": str(parent_run_id) if parent_run_id else None
            }
        )

    def on_llm_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any
    ) -> None:
        """Log LLM error."""
        self._macaw.log_event(
            event_type="llm_error",
            action="error",
            target="llm",
            metadata={
                "run_id": str(run_id),
                "error": str(error)
            }
        )

    # Tool Callbacks

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any
    ) -> None:
        """Log tool invocation start."""
        tool_name = serialized.get("name", "unknown")
        self._macaw.log_event(
            event_type="tool_start",
            action="start",
            target=f"tool:{tool_name}",
            metadata={
                "run_id": str(run_id),
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
                "tool": tool_name,
                "input_length": len(input_str)
            }
        )

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any
    ) -> None:
        """Log tool completion."""
        self._macaw.log_event(
            event_type="tool_end",
            action="complete",
            target="tool",
            metadata={
                "run_id": str(run_id),
                "output_length": len(str(output)) if output else 0
            }
        )

    def on_tool_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any
    ) -> None:
        """Log tool error."""
        self._macaw.log_event(
            event_type="tool_error",
            action="error",
            target="tool",
            metadata={
                "run_id": str(run_id),
                "error": str(error)
            }
        )

    # Chain Callbacks

    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any
    ) -> None:
        """Log chain execution start."""
        chain_name = serialized.get("name", "unknown")
        self._macaw.log_event(
            event_type="chain_start",
            action="start",
            target=f"chain:{chain_name}",
            metadata={
                "run_id": str(run_id),
                "parent_run_id": str(parent_run_id) if parent_run_id else None,
                "chain": chain_name,
                "input_keys": list(inputs.keys())
            }
        )

    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any
    ) -> None:
        """Log chain completion."""
        self._macaw.log_event(
            event_type="chain_end",
            action="complete",
            target="chain",
            metadata={
                "run_id": str(run_id),
                "output_keys": list(outputs.keys()) if outputs else []
            }
        )

    def on_chain_error(
        self,
        error: Union[Exception, KeyboardInterrupt],
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any
    ) -> None:
        """Log chain error."""
        self._macaw.log_event(
            event_type="chain_error",
            action="error",
            target="chain",
            metadata={
                "run_id": str(run_id),
                "error": str(error)
            }
        )

    # Agent Callbacks

    def on_agent_action(
        self,
        action: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any
    ) -> None:
        """Log agent action."""
        self._macaw.log_event(
            event_type="agent_action",
            action="action",
            target="agent",
            metadata={
                "run_id": str(run_id),
                "tool": getattr(action, 'tool', 'unknown'),
                "tool_input": str(getattr(action, 'tool_input', ''))[:100]
            }
        )

    def on_agent_finish(
        self,
        finish: Any,
        *,
        run_id: UUID,
        parent_run_id: Optional[UUID] = None,
        **kwargs: Any
    ) -> None:
        """Log agent finish."""
        self._macaw.log_event(
            event_type="agent_finish",
            action="complete",
            target="agent",
            metadata={
                "run_id": str(run_id),
                "return_values": list(getattr(finish, 'return_values', {}).keys())
            }
        )
