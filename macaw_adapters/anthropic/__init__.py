"""
MACAW Anthropic Adapter - Secure drop-in replacement for Anthropic client.

Usage:
    # Before
    from anthropic import Anthropic
    client = Anthropic()

    # After (one line change!)
    from macaw_adapters.anthropic import SecureAnthropic
    client = SecureAnthropic()

Features:
    - Drop-in replacement for Anthropic client
    - Policy-enforced tool execution
    - Cryptographic audit trail
    - Multi-user identity binding
"""

from macaw_adapters.anthropic.secure_anthropic import SecureAnthropic

__all__ = ["SecureAnthropic"]
