#!/usr/bin/env python3
"""
openai_1a_dropin_simple.py - Drop-in replacement for OpenAI client

The simplest integration path - just replace your import and it works.
No Identity Provider needed.

Prerequisites:
    - MACAW SDK installed (pip install macaw-client macaw-adapters)
    - OPENAI_API_KEY environment variable

Run:
    export OPENAI_API_KEY=sk-...
    python openai_1a_dropin_simple.py
"""

import os
import sys

# BEFORE: from openai import OpenAI
# AFTER:
from macaw_adapters.openai import SecureOpenAI

def main():
    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY environment variable")
        print("  export OPENAI_API_KEY=sk-...")
        return

    print("=" * 60)
    print("Example 1a: Drop-in Replacement (OpenAI)")
    print("=" * 60)
    print("\nPath: Direct on service (simplest)")
    print("Use when: Single app, no user distinction, app-level policies")

    # Create SecureOpenAI - just like regular OpenAI client
    # Add intent_policy to restrict to GPT-3.5 only (no GPT-4)
    client = SecureOpenAI(
        app_name="my-simple-app",
        intent_policy={
            "constraints": {
                "parameters": {
                    "tool:*/generate": {
                        "model": ["gpt-3.5-turbo"],  # Only GPT-3.5 allowed
                        "max_tokens": {"max": 200}
                    }
                }
            }
        }
    )

    print(f"\nService registered: {client.server_id}")
    print(f"Mode: {client._mode}")
    print("Policy: GPT-3.5 only, max 200 tokens")

    # Same API as OpenAI - no changes needed
    print("\n--- Test 1: Allowed model (gpt-3.5-turbo) ---")
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        max_tokens=100,
        messages=[
            {"role": "user", "content": "What is compound interest? Answer briefly."}
        ]
    )

    print(f"Model: {response.model}")
    print(f"Response: {response.choices[0].message.content}")

    # Policy enforcement - try a blocked model
    print("\n--- Test 2: Blocked model (gpt-4) ---")
    try:
        response = client.chat.completions.create(
            model="gpt-4",  # NOT in allowed list!
            max_tokens=100,
            messages=[
                {"role": "user", "content": "What is compound interest?"}
            ]
        )
        print(f"Unexpected success - should have been blocked!")
        print(f"Response: {response.choices[0].message.content[:100]}...")
    except Exception as e:
        print(f"Correctly blocked: {e}")

    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err = str(e)
        print("\n" + "=" * 60)
        if "OPENAI_API_KEY" in err or "api_key" in err.lower():
            print("ERROR: OpenAI API key not configured")
            print("Fix: export OPENAI_API_KEY=sk-...")
        else:
            print(f"ERROR: {e}")
        print("=" * 60)
        sys.exit(1)
