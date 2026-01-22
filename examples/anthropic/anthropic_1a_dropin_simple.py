#!/usr/bin/env python3
"""
Example 1a: Drop-in Replacement (Anthropic)

The simplest path - just replace your import and it works.
Use this when: Single app, no user distinction, app-level policies.

Run with:
    PYTHONPATH=/path/to/secureAI python anthropic_1a_dropin_simple.py
"""

import os

# BEFORE: from anthropic import Anthropic
# AFTER:
from macaw_adapters.anthropic import SecureAnthropic


def main():
    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY environment variable")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        return

    print("=" * 60)
    print("Example 1a: Drop-in Replacement (Anthropic)")
    print("=" * 60)
    print("\nPath: Direct on service (simplest)")
    print("Use when: Single app, no user distinction, app-level policies")

    # Create SecureAnthropic - just like regular Anthropic client
    # Add intent_policy to restrict to Haiku only (no Sonnet/Opus)
    client = SecureAnthropic(
        app_name="my-simple-app",
        intent_policy={
            "constraints": {
                "parameters": {
                    "tool:*/generate": {
                        "model": ["claude-3-haiku-20240307"],  # Only Haiku allowed
                        "max_tokens": {"max": 200}
                    }
                }
            }
        }
    )

    print(f"\nService registered: {client.server_id}")
    print(f"Mode: {client._mode}")
    print("Policy: Haiku only, max 200 tokens")

    # Same API as Anthropic - no changes needed
    print("\n--- Test 1: Allowed model (claude-3-haiku) ---")
    response = client.messages.create(
        model="claude-3-haiku-20240307",
        max_tokens=100,
        messages=[
            {"role": "user", "content": "What is compound interest? Answer briefly."}
        ]
    )

    print(f"Model: {response.model}")
    print(f"Response: {response.content[0].text}")

    # Policy enforcement - try a blocked model
    print("\n--- Test 2: Blocked model (claude-4.5-opus) ---")
    try:
        response = client.messages.create(
            model="claude-opus-4-5-20251101",  # NOT in allowed list!
            max_tokens=100,
            messages=[
                {"role": "user", "content": "What is compound interest?"}
            ]
        )
        print(f"Unexpected success - should have been blocked!")
        print(f"Response: {response.content[0].text[:100]}...")
    except Exception as e:
        print(f"Correctly blocked: {e}")

    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
