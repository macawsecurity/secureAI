#!/usr/bin/env python3
"""
litellm_1a_dropin_simple.py - Drop-in replacement for LiteLLM

The simplest integration path - just replace your import and it works.
No Identity Provider needed. Tests multiple providers through unified API.

Prerequisites:
    - MACAW SDK installed (pip install macaw-client macaw-adapters[litellm])
    - OPENAI_API_KEY and/or ANTHROPIC_API_KEY environment variables

Run:
    export OPENAI_API_KEY=sk-...
    export ANTHROPIC_API_KEY=sk-ant-...
    python litellm_1a_dropin_simple.py
"""

import os
import sys

# BEFORE: import litellm
# AFTER:
from macaw_adapters.litellm import SecureLiteLLM


def main():
    # Check for at least one API key
    has_openai = bool(os.environ.get("OPENAI_API_KEY"))
    has_anthropic = bool(os.environ.get("ANTHROPIC_API_KEY"))

    if not has_openai and not has_anthropic:
        print("Set at least one API key:")
        print("  export OPENAI_API_KEY=sk-...")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        return

    print("=" * 60)
    print("Example 1a: Drop-in Replacement (LiteLLM)")
    print("=" * 60)
    print("\nPath: Direct on service (simplest)")
    print("Use when: Single app, multiple providers, app-level policies")
    print(f"\nProviders available: OpenAI={has_openai}, Anthropic={has_anthropic}")

    # Define allowed models - only cheaper/faster models
    allowed_models = []
    if has_openai:
        allowed_models.append("openai/gpt-3.5-turbo")
    if has_anthropic:
        allowed_models.append("anthropic/claude-3-haiku-20240307")

    # Create SecureLiteLLM with policy restricting to allowed models
    client = SecureLiteLLM(
        app_name="my-litellm-app",
        intent_policy={
            "constraints": {
                "parameters": {
                    "tool:*/generate": {
                        "model": allowed_models,
                        "max_tokens": {"max": 200}
                    }
                }
            }
        }
    )

    print(f"\nService registered: {client.server_id}")
    print(f"Mode: {client._mode}")
    print(f"Policy: Only {allowed_models}, max 200 tokens")

    # Test 1: OpenAI backend (if available)
    if has_openai:
        print("\n--- Test 1: OpenAI backend (gpt-3.5-turbo) ---")
        response = client.chat.completions.create(
            model="openai/gpt-3.5-turbo",
            max_tokens=100,
            messages=[
                {"role": "user", "content": "What is 2+2? One word answer."}
            ]
        )
        print(f"Model: {response.model}")
        print(f"Response: {response.choices[0].message.content}")

    # Test 2: Anthropic backend (if available)
    if has_anthropic:
        print("\n--- Test 2: Anthropic backend (claude-3-haiku) ---")
        response = client.chat.completions.create(
            model="anthropic/claude-3-haiku-20240307",
            max_tokens=100,
            messages=[
                {"role": "user", "content": "What is 3+3? One word answer."}
            ]
        )
        print(f"Model: {response.model}")
        print(f"Response: {response.choices[0].message.content}")

    # Test 3: Policy enforcement - try a blocked model
    print("\n--- Test 3: Policy enforcement (blocked model) ---")
    blocked_model = "openai/gpt-4" if has_openai else "anthropic/claude-3-5-sonnet-20241022"
    print(f"Trying blocked model: {blocked_model}")

    try:
        response = client.chat.completions.create(
            model=blocked_model,
            max_tokens=100,
            messages=[
                {"role": "user", "content": "Hello"}
            ]
        )
        print(f"Unexpected success - should have been blocked!")
        print(f"Response: {response.choices[0].message.content[:50]}...")
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
        if "api_key" in err.lower():
            print("ERROR: API key not configured")
            print("Fix: export OPENAI_API_KEY=sk-... or ANTHROPIC_API_KEY=sk-ant-...")
        else:
            print(f"ERROR: {e}")
        print("=" * 60)
        sys.exit(1)
