"""
MACAW ChatOpenAI - Drop-in replacement for langchain_openai.ChatOpenAI with MACAW protection.

Usage:
    # Instead of: from langchain_openai import ChatOpenAI
    from macaw_adapters.langchain.openai import ChatOpenAI

    # Same API, MACAW security is invisible
    llm = ChatOpenAI(model="gpt-4")
    response = llm.invoke("Hello, world!")

Security:
    This adapter uses SecureOpenAI internally, which routes all LLM calls through
    MACAW's Policy Enforcement Point (PEP) via invoke_tool. This ensures:
    - Policy enforcement on every LLM call
    - Cryptographic audit logging
    - Per-user identity propagation via bind_to_user
"""

import logging
from typing import Any, Dict, Iterator, List, Optional

logger = logging.getLogger(__name__)

# Global registry of ChatOpenAI instances for cleanup
_instances: List['ChatOpenAI'] = []


class ChatOpenAI:
    """
    Drop-in replacement for langchain_openai.ChatOpenAI with MACAW protection.

    Uses SecureOpenAI internally to route all LLM calls through MACAW's PEP.
    This ensures policy enforcement, not just logging.

    MACAW is completely invisible - use exactly like native LangChain.
    """

    def __init__(
        self,
        model: str = "gpt-4",
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        organization: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: int = 2,
        **kwargs
    ):
        """
        Initialize SecureChatOpenAI.

        Args:
            model: OpenAI model name (e.g., "gpt-4", "gpt-3.5-turbo")
            temperature: Sampling temperature (0.0 to 2.0)
            max_tokens: Maximum tokens to generate
            api_key: OpenAI API key (or use OPENAI_API_KEY env var)
            base_url: Custom API base URL
            organization: OpenAI organization ID
            timeout: Request timeout in seconds
            max_retries: Maximum retry attempts
            **kwargs: Additional arguments
        """
        # Store configuration
        self.model_name = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self._kwargs = kwargs

        # Store optional config for reference (not passed to SecureOpenAI)
        self._base_url = base_url
        self._organization = organization
        self._timeout = timeout
        self._max_retries = max_retries

        # Create SecureOpenAI internally - it handles its own MACAWClient
        # SecureOpenAI accepts: api_key, app_name, intent_policy
        from macaw_adapters.openai import SecureOpenAI

        self._secure_openai = SecureOpenAI(
            app_name="langchain-openai",
            api_key=api_key
        )

        # Track for cleanup
        _instances.append(self)

        logger.debug(f"[ChatOpenAI] Created with SecureOpenAI backend, model={model}")

    def _to_openai_messages(self, input_data: Any) -> List[Dict[str, str]]:
        """Convert LangChain input to OpenAI message format."""
        if isinstance(input_data, str):
            return [{"role": "user", "content": input_data}]

        if isinstance(input_data, list):
            messages = []
            for msg in input_data:
                if hasattr(msg, 'type') and hasattr(msg, 'content'):
                    # LangChain message object (HumanMessage, AIMessage, etc.)
                    role_map = {
                        "human": "user",
                        "ai": "assistant",
                        "system": "system",
                        "function": "function",
                        "tool": "tool"
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

    def _to_langchain_message(self, openai_response: Any) -> Any:
        """Convert OpenAI ChatCompletion to LangChain AIMessage."""
        try:
            from langchain_core.messages import AIMessage

            # Handle dict response
            if isinstance(openai_response, dict):
                choices = openai_response.get("choices", [])
                if choices:
                    content = choices[0].get("message", {}).get("content", "")
                    return AIMessage(content=content)
                return AIMessage(content="")

            # Handle ChatCompletion object
            if hasattr(openai_response, 'choices') and openai_response.choices:
                content = openai_response.choices[0].message.content or ""
                return AIMessage(content=content)

            return AIMessage(content=str(openai_response))

        except ImportError:
            # langchain_core not available, return raw response
            logger.warning("langchain_core not installed, returning raw response")
            return openai_response

    def _to_langchain_chunk(self, openai_chunk: Any) -> Any:
        """Convert OpenAI streaming chunk to LangChain AIMessageChunk."""
        try:
            from langchain_core.messages import AIMessageChunk

            # Handle dict chunk
            if isinstance(openai_chunk, dict):
                choices = openai_chunk.get("choices", [])
                if choices:
                    delta = choices[0].get("delta", {})
                    content = delta.get("content", "")
                    return AIMessageChunk(content=content)
                return AIMessageChunk(content="")

            # Handle ChatCompletionChunk object
            if hasattr(openai_chunk, 'choices') and openai_chunk.choices:
                delta = openai_chunk.choices[0].delta
                content = delta.content if delta and delta.content else ""
                return AIMessageChunk(content=content)

            return AIMessageChunk(content="")

        except ImportError:
            # Return raw chunk
            return openai_chunk

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
        # Convert to OpenAI format
        messages = self._to_openai_messages(input)

        # Build params
        params = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
        }
        if self.max_tokens:
            params["max_tokens"] = self.max_tokens

        # Merge additional kwargs
        params.update(kwargs)

        # Call SecureOpenAI (routes through PEP!)
        response = self._secure_openai.chat.completions.create(**params)

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
        # Convert to OpenAI format
        messages = self._to_openai_messages(input)

        # Build params
        params = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "stream": True,
        }
        if self.max_tokens:
            params["max_tokens"] = self.max_tokens

        params.update(kwargs)

        # Stream from SecureOpenAI (routes through PEP!)
        for chunk in self._secure_openai.chat.completions.create(**params):
            yield self._to_langchain_chunk(chunk)

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
        # Process each input through invoke (each goes through PEP)
        return [self.invoke(input, config=config, **kwargs) for input in inputs]

    async def ainvoke(self, input: Any, config: Optional[Dict] = None, **kwargs) -> Any:
        """Async invoke with MACAW protection."""
        # For now, delegate to sync version
        # TODO: Add true async support when SecureOpenAI supports it
        return self.invoke(input, config=config, **kwargs)

    async def astream(self, input: Any, config: Optional[Dict] = None, **kwargs):
        """Async stream with MACAW protection."""
        # Yield from sync stream
        for chunk in self.stream(input, config=config, **kwargs):
            yield chunk

    async def abatch(self, inputs: List[Any], config: Optional[Dict] = None, **kwargs) -> List:
        """Async batch with MACAW protection."""
        return self.batch(inputs, config=config, **kwargs)

    def bind_to_user(self, user_client: 'MACAWClient') -> 'BoundChatOpenAI':
        """
        Bind this LLM to a specific user's identity.

        Returns a BoundChatOpenAI that routes all calls through the user's
        MACAWClient for per-user policy enforcement.

        Args:
            user_client: MACAWClient with user identity (from RemoteIdentityProvider)

        Returns:
            BoundChatOpenAI instance
        """
        return BoundChatOpenAI(self, user_client)

    # Pass-through properties to match LangChain interface
    @property
    def model(self) -> str:
        return self.model_name

    def bind(self, **kwargs):
        """Bind arguments to the LLM (LangChain compatibility)."""
        # Create a new instance with merged kwargs
        new_kwargs = {**self._kwargs, **kwargs}
        return ChatOpenAI(
            model=self.model_name,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
            **new_kwargs
        )

    def with_config(self, config: Dict):
        """Return self with config (LangChain compatibility)."""
        # Config is handled per-call, not stored
        return self

    def cleanup(self):
        """Clean up resources."""
        if hasattr(self, '_secure_openai') and self._secure_openai:
            try:
                self._secure_openai.cleanup()
            except Exception as e:
                logger.debug(f"Cleanup error (may be expected): {e}")


class BoundChatOpenAI:
    """
    Per-user wrapper for ChatOpenAI.

    Created via ChatOpenAI.bind_to_user(user_client).
    Routes all calls through the user's identity for per-user policy enforcement.
    """

    def __init__(self, parent: ChatOpenAI, user_client: 'MACAWClient'):
        self._parent = parent
        self._user_client = user_client

        # Get bound SecureOpenAI for this user
        self._bound_openai = parent._secure_openai.bind_to_user(user_client)

    def _to_openai_messages(self, input_data: Any) -> List[Dict[str, str]]:
        """Delegate to parent's conversion."""
        return self._parent._to_openai_messages(input_data)

    def _to_langchain_message(self, openai_response: Any) -> Any:
        """Delegate to parent's conversion."""
        return self._parent._to_langchain_message(openai_response)

    def _to_langchain_chunk(self, openai_chunk: Any) -> Any:
        """Delegate to parent's conversion."""
        return self._parent._to_langchain_chunk(openai_chunk)

    def invoke(self, input: Any, config: Optional[Dict] = None, **kwargs) -> Any:
        """Invoke with user identity."""
        messages = self._to_openai_messages(input)

        params = {
            "model": self._parent.model_name,
            "messages": messages,
            "temperature": self._parent.temperature,
        }
        if self._parent.max_tokens:
            params["max_tokens"] = self._parent.max_tokens
        params.update(kwargs)

        # Call through bound SecureOpenAI (user identity!)
        response = self._bound_openai.chat.completions.create(**params)
        return self._to_langchain_message(response)

    def stream(self, input: Any, config: Optional[Dict] = None, **kwargs) -> Iterator:
        """Stream with user identity."""
        messages = self._to_openai_messages(input)

        params = {
            "model": self._parent.model_name,
            "messages": messages,
            "temperature": self._parent.temperature,
            "stream": True,
        }
        if self._parent.max_tokens:
            params["max_tokens"] = self._parent.max_tokens
        params.update(kwargs)

        for chunk in self._bound_openai.chat.completions.create(**params):
            yield self._to_langchain_chunk(chunk)

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
    """Clean up all ChatOpenAI instances."""
    for instance in _instances:
        try:
            instance.cleanup()
        except Exception as e:
            logger.debug(f"Cleanup error: {e}")
    _instances.clear()
