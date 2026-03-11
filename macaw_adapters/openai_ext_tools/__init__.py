"""
MACAW OpenAI Adapter with Explicit Tools - Enhanced observability version.

This version uses a two-client architecture:
- macaw_client: Primary, owns LLM operations (externally reachable)
- _tools_client: Internal, owns user tools (not externally reachable)

Usage:
    # Standard version
    from macaw_adapters.openai import SecureOpenAI

    # Explicit tools version (this module)
    from macaw_adapters.openai_ext_tools import SecureOpenAI
    client = SecureOpenAI()

Features:
    - Drop-in replacement for OpenAI client
    - Two-client architecture for explicit tool observability
    - Tools isolated on internal client
    - Clear trace flow: LLM → Tools
"""

from macaw_adapters.openai_ext_tools.secure_openai import SecureOpenAI

__all__ = ["SecureOpenAI"]
