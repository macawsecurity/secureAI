"""
MACAW ChatAnthropic - Drop-in replacement for langchain_anthropic.ChatAnthropic with MACAW protection.

Usage:
    # Instead of: from langchain_anthropic import ChatAnthropic
    from macaw_adapters.langchain.anthropic import ChatAnthropic

    # Same API, MACAW security is invisible
    llm = ChatAnthropic(model="claude-3-opus-20240229")
    response = llm.invoke("Hello, world!")
"""

import logging
from typing import Any, Dict, Iterator, List, Optional

from macaw_client import MACAWClient
from ._utils import get_or_create_client, cleanup_client

logger = logging.getLogger(__name__)


class ChatAnthropic:
    """
    Drop-in replacement for langchain_anthropic.ChatAnthropic with MACAW protection.

    This class wraps the original ChatAnthropic and routes all LLM calls through
    MACAWClient for policy enforcement, audit logging, and security.

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
        macaw_client: Optional[MACAWClient] = None,
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
            macaw_client: Optional pre-configured MACAWClient
            **kwargs: Additional arguments passed to underlying ChatAnthropic
        """
        # Store configuration
        self.model_name = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = timeout
        self.max_retries = max_retries
        self._kwargs = kwargs

        # Initialize MACAW client
        self._macaw = macaw_client or get_or_create_client("langchain-anthropic")

        # Lazy-load the actual langchain_anthropic.ChatAnthropic
        self._llm = None

    def _get_llm(self):
        """Lazy-load the underlying ChatAnthropic instance."""
        if self._llm is None:
            try:
                from langchain_anthropic import ChatAnthropic as _ChatAnthropic

                # Build kwargs, only including non-None values
                # langchain_anthropic doesn't accept api_key=None
                llm_kwargs = {
                    "model": self.model_name,
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                    "max_retries": self.max_retries,
                    **self._kwargs
                }
                if self.api_key is not None:
                    llm_kwargs["api_key"] = self.api_key
                if self.base_url is not None:
                    llm_kwargs["base_url"] = self.base_url
                if self.timeout is not None:
                    llm_kwargs["timeout"] = self.timeout

                self._llm = _ChatAnthropic(**llm_kwargs)
            except ImportError:
                raise ImportError(
                    "langchain_anthropic is required. Install with: pip install langchain-anthropic"
                )
        return self._llm

    def _format_input(self, input_data: Any) -> str:
        """Convert various input formats to string for MACAW."""
        if isinstance(input_data, str):
            return input_data
        elif isinstance(input_data, list):
            # List of messages
            parts = []
            for msg in input_data:
                if hasattr(msg, 'content'):
                    parts.append(str(msg.content))
                elif isinstance(msg, dict):
                    parts.append(str(msg.get('content', msg)))
                else:
                    parts.append(str(msg))
            return "\n".join(parts)
        else:
            return str(input_data)

    def invoke(self, input: Any, config: Optional[Dict] = None, **kwargs) -> Any:
        """
        Invoke the LLM with MACAW protection.

        Args:
            input: The input prompt (string or list of messages)
            config: Optional configuration dict
            **kwargs: Additional arguments

        Returns:
            LLM response (AIMessage or similar)
        """
        llm = self._get_llm()

        # Route through MACAW for policy/audit
        if self._macaw:
            prompt_str = self._format_input(input)
            logger.debug(f"[SecureChatAnthropic] Routing invoke through MACAW")

            # Log the invocation through MACAW
            self._macaw.log_event(
                event_type="llm_invoke",
                action="invoke",
                target=f"anthropic:{self.model_name}",
                metadata={
                    "model": self.model_name,
                    "prompt_length": len(prompt_str),
                    "temperature": self.temperature
                }
            )

        # Call underlying LLM
        return llm.invoke(input, config=config, **kwargs)

    def stream(self, input: Any, config: Optional[Dict] = None, **kwargs) -> Iterator:
        """
        Stream responses from the LLM with MACAW protection.

        Args:
            input: The input prompt
            config: Optional configuration dict
            **kwargs: Additional arguments

        Yields:
            Streaming chunks from the LLM
        """
        llm = self._get_llm()

        # Route through MACAW for policy/audit
        if self._macaw:
            prompt_str = self._format_input(input)
            logger.debug(f"[SecureChatAnthropic] Routing stream through MACAW")

            self._macaw.log_event(
                event_type="llm_stream",
                action="stream",
                target=f"anthropic:{self.model_name}",
                metadata={
                    "model": self.model_name,
                    "prompt_length": len(prompt_str)
                }
            )

        # Stream from underlying LLM
        yield from llm.stream(input, config=config, **kwargs)

    def batch(self, inputs: List[Any], config: Optional[Dict] = None, **kwargs) -> List:
        """
        Batch invoke the LLM with MACAW protection.

        Args:
            inputs: List of input prompts
            config: Optional configuration dict
            **kwargs: Additional arguments

        Returns:
            List of LLM responses
        """
        llm = self._get_llm()

        # Route through MACAW for policy/audit
        if self._macaw:
            logger.debug(f"[SecureChatAnthropic] Routing batch ({len(inputs)} items) through MACAW")

            self._macaw.log_event(
                event_type="llm_batch",
                action="batch",
                target=f"anthropic:{self.model_name}",
                metadata={
                    "model": self.model_name,
                    "batch_size": len(inputs)
                }
            )

        return llm.batch(inputs, config=config, **kwargs)

    async def ainvoke(self, input: Any, config: Optional[Dict] = None, **kwargs) -> Any:
        """Async invoke with MACAW protection."""
        llm = self._get_llm()

        if self._macaw:
            prompt_str = self._format_input(input)
            self._macaw.log_event(
                event_type="llm_ainvoke",
                action="ainvoke",
                target=f"anthropic:{self.model_name}",
                metadata={"model": self.model_name, "prompt_length": len(prompt_str)}
            )

        return await llm.ainvoke(input, config=config, **kwargs)

    async def astream(self, input: Any, config: Optional[Dict] = None, **kwargs):
        """Async stream with MACAW protection."""
        llm = self._get_llm()

        if self._macaw:
            self._macaw.log_event(
                event_type="llm_astream",
                action="astream",
                target=f"anthropic:{self.model_name}",
                metadata={"model": self.model_name}
            )

        async for chunk in llm.astream(input, config=config, **kwargs):
            yield chunk

    async def abatch(self, inputs: List[Any], config: Optional[Dict] = None, **kwargs) -> List:
        """Async batch with MACAW protection."""
        llm = self._get_llm()

        if self._macaw:
            self._macaw.log_event(
                event_type="llm_abatch",
                action="abatch",
                target=f"anthropic:{self.model_name}",
                metadata={"model": self.model_name, "batch_size": len(inputs)}
            )

        return await llm.abatch(inputs, config=config, **kwargs)

    # Pass-through properties to match LangChain interface
    @property
    def model(self) -> str:
        return self.model_name

    def bind(self, **kwargs):
        """Bind arguments to the LLM."""
        llm = self._get_llm()
        return llm.bind(**kwargs)

    def with_config(self, config: Dict):
        """Return a new instance with config."""
        llm = self._get_llm()
        return llm.with_config(config)

    def __getattr__(self, name: str) -> Any:
        """Delegate unknown attributes to underlying LLM."""
        if name.startswith('_'):
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")
        llm = self._get_llm()
        return getattr(llm, name)


def cleanup():
    """Clean up the langchain-anthropic MACAW client."""
    cleanup_client("langchain-anthropic")
