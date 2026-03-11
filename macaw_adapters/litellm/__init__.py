"""
MACAW-secured LiteLLM adapter.

Drop-in replacement for litellm with MACAW security.
Supports 100+ LLM providers through LiteLLM's unified interface.

Usage:
    # Drop-in replacement
    from macaw_adapters import litellm

    response = litellm.completion(
        model="groq/llama3-70b-8192",
        messages=[{"role": "user", "content": "Hello"}]
    )

    # With explicit app_name
    response = litellm.completion(
        model="together_ai/meta-llama/Llama-3-70b",
        messages=[...],
        app_name="my-service"
    )

    # With custom endpoint (vLLM, Ollama, etc.)
    response = litellm.completion(
        model="openai/llama3",
        messages=[...],
        api_base="http://localhost:8000/v1"
    )

    # Class-based usage for advanced control
    from macaw_adapters.litellm import SecureLiteLLM

    client = SecureLiteLLM(app_name="my-app", intent_policy={...})
    response = client.completion(model="groq/llama3-70b", messages=[...])

For more information, visit: https://macawsecurity.ai
"""

# Re-export everything from litellm for drop-in compatibility
from litellm import *

# Import our secure wrapper
from .secure_litellm import SecureLiteLLM, BoundSecureLiteLLM

# Default client instance (lazy initialization)
_default_client = None
_default_app_name = None


def _get_client(app_name=None, api_base=None, api_key=None, intent_policy=None):
    """Get or create the default SecureLiteLLM client."""
    global _default_client, _default_app_name

    # Use provided app_name or default
    app = app_name or "macaw-litellm"

    # Create new client if needed
    if _default_client is None or (app_name and app_name != _default_app_name):
        _default_client = SecureLiteLLM(
            app_name=app,
            api_base=api_base,
            api_key=api_key,
            intent_policy=intent_policy
        )
        _default_app_name = app

    return _default_client


def completion(model, messages, app_name=None, api_base=None, api_key=None,
               intent_policy=None, **kwargs):
    """
    Secured drop-in replacement for litellm.completion().

    All LLM calls go through MACAW policy enforcement.

    Args:
        model: Model identifier (e.g., "groq/llama3-70b-8192", "gpt-4", etc.)
        messages: List of message dicts
        app_name: Optional MACAW app name (default: macaw-litellm)
        api_base: Optional custom API endpoint
        api_key: Optional API key (uses env vars by default)
        intent_policy: Optional MACAW intent policy
        **kwargs: Additional arguments passed to LiteLLM

    Returns:
        ModelResponse from LiteLLM
    """
    client = _get_client(app_name, api_base, api_key, intent_policy)
    return client.completion(model=model, messages=messages, **kwargs)


async def acompletion(model, messages, app_name=None, api_base=None, api_key=None,
                      intent_policy=None, **kwargs):
    """
    Secured async drop-in replacement for litellm.acompletion().

    Note: Currently wraps sync completion. Full async support coming soon.
    """
    # TODO: Implement proper async support
    return completion(model, messages, app_name, api_base, api_key, intent_policy, **kwargs)


def embedding(model, input, app_name=None, api_base=None, api_key=None,
              intent_policy=None, **kwargs):
    """
    Secured drop-in replacement for litellm.embedding().
    """
    client = _get_client(app_name, api_base, api_key, intent_policy)
    return client.embeddings.create(model=model, input=input, **kwargs)


async def aembedding(model, input, app_name=None, api_base=None, api_key=None,
                     intent_policy=None, **kwargs):
    """
    Secured async drop-in replacement for litellm.aembedding().

    Note: Currently wraps sync embedding. Full async support coming soon.
    """
    return embedding(model, input, app_name, api_base, api_key, intent_policy, **kwargs)


def text_completion(model, prompt, app_name=None, api_base=None, api_key=None,
                    intent_policy=None, **kwargs):
    """
    Secured drop-in replacement for litellm.text_completion().
    """
    client = _get_client(app_name, api_base, api_key, intent_policy)
    return client.completions.create(model=model, prompt=prompt, **kwargs)


# Export all
__all__ = [
    # Secured classes
    "SecureLiteLLM",
    "BoundSecureLiteLLM",
    # Secured drop-in functions
    "completion",
    "acompletion",
    "embedding",
    "aembedding",
    "text_completion",
]
