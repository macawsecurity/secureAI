"""
MACAW Memory Classes - Drop-in replacements for LangChain memory with MACAW context backing.

Usage:
    # Instead of: from langchain.memory import ConversationBufferMemory
    from macaw_adapters.langchain.memory import ConversationBufferMemory

    # Same API, MACAW context vault backing
    memory = ConversationBufferMemory()
    chain = ConversationChain(llm=llm, memory=memory)
"""

import logging
import uuid
from typing import Any, Dict, List, Optional

from macaw_client import MACAWClient
from ._utils import get_or_create_client, cleanup_client

logger = logging.getLogger(__name__)


class ConversationBufferMemory:
    """
    Drop-in replacement for LangChain's ConversationBufferMemory with MACAW backing.

    This memory class stores conversation history in MACAW's secure context vault,
    providing audit logging and secure storage for all memory operations.
    """

    def __init__(
        self,
        memory_key: str = "history",
        input_key: str = "input",
        output_key: str = "output",
        human_prefix: str = "Human",
        ai_prefix: str = "AI",
        return_messages: bool = False,
        session_id: Optional[str] = None,
        macaw_client: Optional[MACAWClient] = None,
        **kwargs
    ):
        """
        Initialize SecureConversationBufferMemory.

        Args:
            memory_key: Key to use for memory in chain context
            input_key: Key for input in chain context
            output_key: Key for output in chain context
            human_prefix: Prefix for human messages
            ai_prefix: Prefix for AI messages
            return_messages: Return messages as list vs string
            session_id: Unique session ID (auto-generated if not provided)
            macaw_client: Optional pre-configured MACAWClient
            **kwargs: Additional arguments
        """
        self.memory_key = memory_key
        self.input_key = input_key
        self.output_key = output_key
        self.human_prefix = human_prefix
        self.ai_prefix = ai_prefix
        self.return_messages = return_messages
        self._kwargs = kwargs

        # Session identification
        self.session_id = session_id or str(uuid.uuid4())
        self._context_key = f"memory:{self.session_id}"

        # Initialize MACAW client
        self._macaw = macaw_client or get_or_create_client("langchain-memory")

        # Local buffer (synced with MACAW context)
        self._buffer: List[Dict[str, str]] = []

        # Load existing memory from context if available
        self._load_from_context()

    def _load_from_context(self) -> None:
        """Load existing memory from MACAW context."""
        if self._macaw:
            stored = self._macaw.context_get(self._context_key)
            if stored and isinstance(stored, list):
                self._buffer = stored
                logger.debug(f"Loaded {len(self._buffer)} messages from context")

    def _save_to_context(self) -> None:
        """Save current memory to MACAW context."""
        if self._macaw:
            self._macaw.context_set(self._context_key, self._buffer)
            logger.debug(f"Saved {len(self._buffer)} messages to context")

    @property
    def buffer(self) -> List[Dict[str, str]]:
        """Get the conversation buffer."""
        return self._buffer

    @property
    def memory_variables(self) -> List[str]:
        """Return memory variables."""
        return [self.memory_key]

    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Load memory variables for chain context.

        Args:
            inputs: Input dictionary (not used for buffer memory)

        Returns:
            Dictionary with memory_key containing conversation history
        """
        # Reload from context to get latest
        self._load_from_context()

        if self.return_messages:
            # Return as list of message objects
            try:
                from langchain_core.messages import HumanMessage, AIMessage
                messages = []
                for msg in self._buffer:
                    if msg.get("type") == "human":
                        messages.append(HumanMessage(content=msg["content"]))
                    else:
                        messages.append(AIMessage(content=msg["content"]))
                return {self.memory_key: messages}
            except ImportError:
                # Fallback to dicts if langchain_core not available
                return {self.memory_key: self._buffer}
        else:
            # Return as formatted string
            lines = []
            for msg in self._buffer:
                prefix = self.human_prefix if msg.get("type") == "human" else self.ai_prefix
                lines.append(f"{prefix}: {msg['content']}")
            return {self.memory_key: "\n".join(lines)}

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, Any]) -> None:
        """
        Save context from this conversation turn.

        Args:
            inputs: Input dictionary with user message
            outputs: Output dictionary with AI response
        """
        # Extract input and output
        input_str = inputs.get(self.input_key, "")
        output_str = outputs.get(self.output_key, "")

        # Handle different output formats
        if hasattr(output_str, 'content'):
            output_str = output_str.content
        elif isinstance(output_str, dict):
            output_str = output_str.get('content', str(output_str))

        # Add to buffer
        if input_str:
            self._buffer.append({"type": "human", "content": str(input_str)})
        if output_str:
            self._buffer.append({"type": "ai", "content": str(output_str)})

        # Persist to MACAW context
        self._save_to_context()

    def clear(self) -> None:
        """Clear memory contents."""
        self._buffer = []
        self._save_to_context()
        logger.debug(f"Cleared memory for session {self.session_id}")

    def add_user_message(self, message: str) -> None:
        """Add a user message to the buffer."""
        self._buffer.append({"type": "human", "content": message})
        self._save_to_context()

    def add_ai_message(self, message: str) -> None:
        """Add an AI message to the buffer."""
        self._buffer.append({"type": "ai", "content": message})
        self._save_to_context()


class ConversationBufferWindowMemory(ConversationBufferMemory):
    """
    Buffer memory that only keeps the last k conversation turns.

    Drop-in replacement for LangChain's ConversationBufferWindowMemory.
    """

    def __init__(self, k: int = 5, **kwargs):
        """
        Initialize with window size.

        Args:
            k: Number of conversation turns to keep
            **kwargs: Arguments passed to ConversationBufferMemory
        """
        super().__init__(**kwargs)
        self.k = k

    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Load only the last k turns."""
        self._load_from_context()

        # Keep only last k*2 messages (k turns = k human + k ai)
        window = self._buffer[-(self.k * 2):]

        if self.return_messages:
            try:
                from langchain_core.messages import HumanMessage, AIMessage
                messages = []
                for msg in window:
                    if msg.get("type") == "human":
                        messages.append(HumanMessage(content=msg["content"]))
                    else:
                        messages.append(AIMessage(content=msg["content"]))
                return {self.memory_key: messages}
            except ImportError:
                return {self.memory_key: window}
        else:
            lines = []
            for msg in window:
                prefix = self.human_prefix if msg.get("type") == "human" else self.ai_prefix
                lines.append(f"{prefix}: {msg['content']}")
            return {self.memory_key: "\n".join(lines)}


class ConversationSummaryMemory:
    """
    Memory that summarizes conversation history.

    Drop-in replacement for LangChain's ConversationSummaryMemory.
    Stores summary in MACAW context vault.
    """

    def __init__(
        self,
        llm: Any = None,
        memory_key: str = "history",
        human_prefix: str = "Human",
        ai_prefix: str = "AI",
        session_id: Optional[str] = None,
        macaw_client: Optional[MACAWClient] = None,
        **kwargs
    ):
        """
        Initialize summary memory.

        Args:
            llm: Language model for summarization
            memory_key: Key for memory in chain context
            human_prefix: Prefix for human messages
            ai_prefix: Prefix for AI messages
            session_id: Unique session ID
            macaw_client: Optional pre-configured MACAWClient
        """
        self.llm = llm
        self.memory_key = memory_key
        self.human_prefix = human_prefix
        self.ai_prefix = ai_prefix
        self._kwargs = kwargs

        # Session identification
        self.session_id = session_id or str(uuid.uuid4())
        self._summary_key = f"memory_summary:{self.session_id}"
        self._buffer_key = f"memory_buffer:{self.session_id}"

        # Initialize MACAW client
        self._macaw = macaw_client or get_or_create_client("langchain-memory")

        # Local state
        self._summary = ""
        self._buffer: List[Dict[str, str]] = []

        # Load existing from context
        self._load_from_context()

    def _load_from_context(self) -> None:
        """Load existing summary and buffer from context."""
        if self._macaw:
            summary = self._macaw.context_get(self._summary_key)
            if summary:
                self._summary = summary

            buffer = self._macaw.context_get(self._buffer_key)
            if buffer and isinstance(buffer, list):
                self._buffer = buffer

    def _save_to_context(self) -> None:
        """Save summary and buffer to context."""
        if self._macaw:
            self._macaw.context_set(self._summary_key, self._summary)
            self._macaw.context_set(self._buffer_key, self._buffer)

    @property
    def memory_variables(self) -> List[str]:
        return [self.memory_key]

    def load_memory_variables(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Load summary as memory variable."""
        self._load_from_context()
        return {self.memory_key: self._summary}

    def save_context(self, inputs: Dict[str, Any], outputs: Dict[str, Any]) -> None:
        """Save context and update summary."""
        input_key = self._kwargs.get('input_key', 'input')
        output_key = self._kwargs.get('output_key', 'output')

        input_str = inputs.get(input_key, "")
        output_str = outputs.get(output_key, "")

        if hasattr(output_str, 'content'):
            output_str = output_str.content

        # Add to buffer
        new_lines = f"{self.human_prefix}: {input_str}\n{self.ai_prefix}: {output_str}"
        self._buffer.append({"input": input_str, "output": output_str})

        # Update summary using LLM if available
        if self.llm:
            try:
                prompt = f"""Progressively summarize the conversation, adding to the previous summary.

Current summary: {self._summary}

New lines of conversation:
{new_lines}

New summary:"""
                response = self.llm.invoke(prompt)
                if hasattr(response, 'content'):
                    self._summary = response.content
                else:
                    self._summary = str(response)
            except Exception as e:
                logger.warning(f"Failed to update summary: {e}")
                # Fallback: append to summary
                self._summary = f"{self._summary}\n{new_lines}" if self._summary else new_lines
        else:
            # No LLM - just concatenate
            self._summary = f"{self._summary}\n{new_lines}" if self._summary else new_lines

        self._save_to_context()

    def clear(self) -> None:
        """Clear memory."""
        self._summary = ""
        self._buffer = []
        self._save_to_context()


def cleanup():
    """Clean up the langchain-memory MACAW client."""
    cleanup_client("langchain-memory")
