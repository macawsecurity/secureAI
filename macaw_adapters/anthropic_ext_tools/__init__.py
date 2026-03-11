"""
MACAW Anthropic Adapter with Explicit Tools - Enhanced observability version.

This version uses a two-client architecture:
- macaw_client: Primary, owns LLM operations (externally reachable)
- _tools_client: Internal, owns user tools (not externally reachable)

Usage:
    # Standard version
    from macaw_adapters.anthropic import SecureAnthropic

    # Explicit tools version (this module)
    from macaw_adapters.anthropic_ext_tools import SecureAnthropic
    client = SecureAnthropic()

Features:
    - Drop-in replacement for Anthropic client
    - Two-client architecture for explicit tool observability
    - Tools isolated on internal client
    - Clear trace flow: LLM → Tools
"""

from macaw_adapters.anthropic_ext_tools.secure_anthropic import SecureAnthropic

__all__ = ["SecureAnthropic"]
