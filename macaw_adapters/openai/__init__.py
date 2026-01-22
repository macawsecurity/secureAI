"""
MACAW OpenAI Adapter - Secure drop-in replacement for OpenAI client.

Usage:
    # Before
    from openai import OpenAI
    client = OpenAI()

    # After (one line change!)
    from macaw_adapters.openai import SecureOpenAI
    client = SecureOpenAI()

Features:
    - Drop-in replacement for OpenAI client
    - Policy-enforced tool execution
    - Cryptographic audit trail
    - Multi-user identity binding
"""

from macaw_adapters.openai.secure_openai import SecureOpenAI

__all__ = ["SecureOpenAI"]
