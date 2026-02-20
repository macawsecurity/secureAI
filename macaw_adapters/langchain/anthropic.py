"""
MACAW ChatAnthropic - Drop-in replacement for langchain_anthropic.ChatAnthropic with MACAW protection.

Usage:
    # Instead of: from langchain_anthropic import ChatAnthropic
    from macaw_adapters.langchain.anthropic import ChatAnthropic

    # Same API, MACAW security is invisible
    llm = ChatAnthropic(model="claude-3-opus-20240229")
    response = llm.invoke("Hello, world!")

Security:
    This adapter uses SecureAnthropic internally, which routes all LLM calls through
    MACAW's Policy Enforcement Point (PEP) via invoke_tool. This ensures:
    - Policy enforcement on every LLM call
    - Cryptographic audit logging
    - Per-user identity propagation via bind_to_user
"""

import logging
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

# Global registry of ChatAnthropic instances for cleanup
_instances: List['ChatAnthropic'] = []


class ChatAnthropic:
    """
    Drop-in replacement for langchain_anthropic.ChatAnthropic with MACAW protection.

    Uses SecureAnthropic internally to route all LLM calls through MACAW's PEP.
    This ensures policy enforcement, not just logging.

    MACAW is completely invisible - use exactly like native LangChain.
    """

    def __init__(
        self,
        model: str = "claude-3-opus-20240229",
        temperature: float = 0.7,
        max_tokens: int = 1024,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: int = 2,
        **kwargs
    ):
        """
        Initialize SecureChatAnthropic.

        Args:
            model: Anthropic model name (e.g., "claude-3-opus-20240229", "claude-3-sonnet-20240229")
            temperature: Sampling temperature (0.0 to 1.0)
            max_tokens: Maximum tokens to generate
            api_key: Anthropic API key (or use ANTHROPIC_API_KEY env var)
            base_url: Custom API base URL
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            **kwargs: Additional arguments
        """
        # Store configuration
        self.model_name = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._kwargs = kwargs

        # Store optional config for reference (not passed to SecureAnthropic)
        self._base_url = base_url
        self._timeout = timeout
        self._max_retries = max_retries

        # Create SecureAnthropic internally - it handles its own MACAWClient
        # SecureAnthropic accepts: api_key, app_name, intent_policy
        from macaw_adapters.anthropic import SecureAnthropic

        self._secure_anthropic = SecureAnthropic(
            app_name="langchain-anthropic",
            api_key=api_key
        )

        # Track for cleanup
        _instances.append(self)

        logger.debug(f"[ChatAnthropic] Created with SecureAnthropic backend, model={model}")

    def _to_anthropic_messages(self, input_data: Any) -> List[Dict[str, str]]:
        """Convert LangChain input to Anthropic message format."""
        if isinstance(input_data, str):
            return [{"role": "user", "content": input_data}]

        if isinstance(input_data, list):
            messages = []
            for msg in input_data:
                if hasattr(msg, 'type') and hasattr(msg, 'content'):
                    # LangChain message object (HumanMessage, AIMessage, etc.)
                    # Anthropic uses "user" and "assistant" roles
                    role_map = {
                        "human": "user",
                        "ai": "assistant",
                        "system": "user",  # Anthropic handles system via system param
                        "function": "user",
                        "tool": "user"
                    }
                    role = role_map.get(msg.type, "user")
                    messages.append({"role": role, "content": str(msg.content)})
                elif isinstance(msg, dict):
                    # Already in dict format
                    messages.append(msg)
                else:
                    # Fallback: treat as user message
                    messages.append({"role": "user", "content": str(msg)})
            return messages

        # Fallback: single user message
        return [{"role": "user", "content": str(input_data)}]

    def _extract_system_message(self, input_data: Any) -> Optional[str]:
        """Extract system message from input if present."""
        if isinstance(input_data, list):
            for msg in input_data:
                if hasattr(msg, 'type') and msg.type == "system":
                    return str(msg.content)
        return None

    def _to_langchain_message(self, anthropic_response: Any) -> Any:
        """Convert Anthropic Message to LangChain AIMessage."""
        try:
            from langchain_core.messages import AIMessage

            # Handle dict response
            if isinstance(anthropic_response, dict):
                content_blocks = anthropic_response.get("content", [])
                if content_blocks:
                    # Concatenate text blocks
                    text_parts = []
                    for block in content_blocks:
                        if isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                        elif isinstance(block, str):
                            text_parts.append(block)
                    return AIMessage(content="".join(text_parts))
                return AIMessage(content="")

            # Handle Message object
            if hasattr(anthropic_response, 'content'):
                content = anthropic_response.content
                if isinstance(content, list):
                    # Content blocks
                    text_parts = []
                    for block in content:
                        if hasattr(block, 'text'):
                            text_parts.append(block.text)
                        elif hasattr(block, 'type') and block.type == "text":
                            text_parts.append(getattr(block, 'text', ''))
                    return AIMessage(content="".join(text_parts))
                return AIMessage(content=str(content))

            return AIMessage(content=str(anthropic_response))

        except ImportError:
            logger.warning("langchain_core not installed, returning raw response")
            return anthropic_response

    def _to_langchain_chunk(self, anthropic_event: Any) -> Any:
        """Convert Anthropic streaming event to LangChain AIMessageChunk."""
        try:
            from langchain_core.messages import AIMessageChunk

            # Handle different event types from Anthropic streaming
            if hasattr(anthropic_event, 'type'):
                if anthropic_event.type == "content_block_delta":
                    delta = getattr(anthropic_event, 'delta', None)
                    if delta and hasattr(delta, 'text'):
                        return AIMessageChunk(content=delta.text)
                elif anthropic_event.type == "text":
                    return AIMessageChunk(content=getattr(anthropic_event, 'text', ''))

            # Handle dict event
            if isinstance(anthropic_event, dict):
                if anthropic_event.get("type") == "content_block_delta":
                    delta = anthropic_event.get("delta", {})
                    return AIMessageChunk(content=delta.get("text", ""))
                elif "text" in anthropic_event:
                    return AIMessageChunk(content=anthropic_event["text"])

            return AIMessageChunk(content="")

        except ImportError:
            return anthropic_event

    def invoke(self, input: Any, config: Optional[Dict] = None, **kwargs) -> Any:
        """
        Invoke the LLM with MACAW protection.

        Args:
            input: The input prompt (string or list of messages)
            config: Optional configuration dict
            **kwargs: Additional arguments

        Returns:
            LLM response (AIMessage)
        """
        # Convert to Anthropic format
        messages = self._to_anthropic_messages(input)
        system_msg = self._extract_system_message(input)

        # Filter out system messages from messages list (handled separately)
        if system_msg:
            messages = [m for m in messages if m.get("role") != "user" or m.get("content") != system_msg]

        # Build params
        params = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }
        if self.temperature is not None:
            params["temperature"] = self.temperature
        if system_msg:
            params["system"] = system_msg

        # Merge additional kwargs
        params.update(kwargs)

        # Call SecureAnthropic (routes through PEP!)
        response = self._secure_anthropic.messages.create(**params)

        # Convert to LangChain format
        return self._to_langchain_message(response)

    def stream(self, input: Any, config: Optional[Dict] = None, **kwargs) -> Iterator:
        """
        Stream responses from the LLM with MACAW protection.

        Args:
            input: The input prompt
            config: Optional configuration dict
            **kwargs: Additional arguments

        Yields:
            Streaming chunks (AIMessageChunk)
        """
        # Convert to Anthropic format
        messages = self._to_anthropic_messages(input)
        system_msg = self._extract_system_message(input)

        if system_msg:
            messages = [m for m in messages if m.get("role") != "user" or m.get("content") != system_msg]

        # Build params
        params = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": self.max_tokens,
        }
        if self.temperature is not None:
            params["temperature"] = self.temperature
        if system_msg:
            params["system"] = system_msg

        params.update(kwargs)

        # Stream from SecureAnthropic (routes through PEP!)
        with self._secure_anthropic.messages.stream(**params) as stream:
            for event in stream:
                chunk = self._to_langchain_chunk(event)
                if chunk:
                    yield chunk

    def batch(self, inputs: List[Any], config: Optional[Dict] = None, **kwargs) -> List:
        """
        Batch invoke the LLM with MACAW protection.

        Args:
            inputs: List of input prompts
            config: Optional configuration dict
            **kwargs: Additional arguments

        Returns:
            List of LLM responses (AIMessage)
        """
        return [self.invoke(input, config=config, **kwargs) for input in inputs]

    async def ainvoke(self, input: Any, config: Optional[Dict] = None, **kwargs) -> Any:
        """Async invoke with MACAW protection."""
        return self.invoke(input, config=config, **kwargs)

    async def astream(self, input: Any, config: Optional[Dict] = None, **kwargs):
        """Async stream with MACAW protection."""
        for chunk in self.stream(input, config=config, **kwargs):
            yield chunk

    async def abatch(self, inputs: List[Any], config: Optional[Dict] = None, **kwargs) -> List:
        """Async batch with MACAW protection."""
        return self.batch(inputs, config=config, **kwargs)

    def bind_to_user(self, user_client: 'MACAWClient') -> 'BoundChatAnthropic':
        """
        Bind this LLM to a specific user's identity.

        Returns a BoundChatAnthropic that routes all calls through the user's
        MACAWClient for per-user policy enforcement.

        Args:
            user_client: MACAWClient with user identity (from RemoteIdentityProvider)

        Returns:
            BoundChatAnthropic instance
        """
        return BoundChatAnthropic(self, user_client)

    # Pass-through properties to match LangChain interface
    @property
    def model(self) -> str:
        return self.model_name

    def bind(self, **kwargs):
        """Bind arguments to the LLM (LangChain compatibility)."""
        new_kwargs = {**self._kwargs, **kwargs}
        return ChatAnthropic(
            model=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            **new_kwargs
        )

    def with_config(self, config: Dict):
        """Return self with config (LangChain compatibility)."""
        return self

    def cleanup(self):
        """Clean up resources."""
        if hasattr(self, '_secure_anthropic') and self._secure_anthropic:
            try:
                self._secure_anthropic.cleanup()
            except Exception as e:
                logger.debug(f"Cleanup error (may be expected): {e}")


class BoundChatAnthropic:
    """
    Per-user wrapper for ChatAnthropic.

    Created via ChatAnthropic.bind_to_user(user_client).
    Routes all calls through the user's identity for per-user policy enforcement.
    """

    def __init__(self, parent: ChatAnthropic, user_client: 'MACAWClient'):
        self._parent = parent
        self._user_client = user_client

        # Get bound SecureAnthropic for this user
        self._bound_anthropic = parent._secure_anthropic.bind_to_user(user_client)

    def _to_anthropic_messages(self, input_data: Any) -> List[Dict[str, str]]:
        return self._parent._to_anthropic_messages(input_data)

    def _extract_system_message(self, input_data: Any) -> Optional[str]:
        return self._parent._extract_system_message(input_data)

    def _to_langchain_message(self, anthropic_response: Any) -> Any:
        return self._parent._to_langchain_message(anthropic_response)

    def _to_langchain_chunk(self, anthropic_event: Any) -> Any:
        return self._parent._to_langchain_chunk(anthropic_event)

    def invoke(self, input: Any, config: Optional[Dict] = None, **kwargs) -> Any:
        """Invoke with user identity."""
        messages = self._to_anthropic_messages(input)
        system_msg = self._extract_system_message(input)

        if system_msg:
            messages = [m for m in messages if m.get("role") != "user" or m.get("content") != system_msg]

        params = {
            "model": self._parent.model_name,
            "messages": messages,
            "max_tokens": self._parent.max_tokens,
        }
        if self._parent.temperature is not None:
            params["temperature"] = self._parent.temperature
        if system_msg:
            params["system"] = system_msg
        params.update(kwargs)

        # Call through bound SecureAnthropic (user identity!)
        response = self._bound_anthropic.messages.create(**params)
        return self._to_langchain_message(response)

    def stream(self, input: Any, config: Optional[Dict] = None, **kwargs) -> Iterator:
        """Stream with user identity."""
        messages = self._to_anthropic_messages(input)
        system_msg = self._extract_system_message(input)

        if system_msg:
            messages = [m for m in messages if m.get("role") != "user" or m.get("content") != system_msg]

        params = {
            "model": self._parent.model_name,
            "messages": messages,
            "max_tokens": self._parent.max_tokens,
        }
        if self._parent.temperature is not None:
            params["temperature"] = self._parent.temperature
        if system_msg:
            params["system"] = system_msg
        params.update(kwargs)

        with self._bound_anthropic.messages.stream(**params) as stream:
            for event in stream:
                chunk = self._to_langchain_chunk(event)
                if chunk:
                    yield chunk

    def batch(self, inputs: List[Any], config: Optional[Dict] = None, **kwargs) -> List:
        """Batch with user identity."""
        return [self.invoke(input, config=config, **kwargs) for input in inputs]

    async def ainvoke(self, input: Any, config: Optional[Dict] = None, **kwargs) -> Any:
        """Async invoke with user identity."""
        return self.invoke(input, config=config, **kwargs)

    async def astream(self, input: Any, config: Optional[Dict] = None, **kwargs):
        """Async stream with user identity."""
        for chunk in self.stream(input, config=config, **kwargs):
            yield chunk

    async def abatch(self, inputs: List[Any], config: Optional[Dict] = None, **kwargs) -> List:
        """Async batch with user identity."""
        return self.batch(inputs, config=config, **kwargs)

    @property
    def model(self) -> str:
        return self._parent.model_name

    @property
    def model_name(self) -> str:
        return self._parent.model_name

    @property
    def temperature(self) -> float:
        return self._parent.temperature


def cleanup():
    """Clean up all ChatAnthropic instances."""
    for instance in _instances:
        try:
            instance.cleanup()
        except Exception as e:
            logger.debug(f"Cleanup error: {e}")
    _instances.clear()
