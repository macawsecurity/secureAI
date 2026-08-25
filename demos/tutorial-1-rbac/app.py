#!/usr/bin/env python3
"""
Role-Based AI Access Control Demo

Demonstrates MACAW policy enforcement with three users:
- alice: Financial Analyst (GPT-3.5 only, 500 tokens)
- bob: Finance Manager (GPT-3.5/4, 2000 tokens)
- carol: IT Administrator (All models, 4000 tokens)
"""

import os
import sys

# MACAW imports
from macaw_adapters.openai import SecureOpenAI
from macaw_client import MACAWClient, RemoteIdentityProvider


# Test users configuration
TEST_USERS = {
    "alice": {
        "password": "Alice123!",
        "role": "Financial Analyst",
        "allowed_models": ["gpt-3.5-turbo"],
        "max_tokens": 500,
    },
    "bob": {
        "password": "Bob@123!",
        "role": "Finance Manager",
        "allowed_models": ["gpt-3.5-turbo", "gpt-4"],
        "max_tokens": 2000,
    },
    "carol": {
        "password": "Carol123!",
        "role": "IT Administrator",
        "allowed_models": ["gpt-3.5-turbo", "gpt-4", "gpt-4-turbo"],
        "max_tokens": 4000,
    },
}


def test_user_with_bind_to_user(openai_service, username: str, user_config: dict):
    """Test a user using the bind_to_user pattern."""
    print(f"\n{'='*60}")
    print(f"Testing {username} ({user_config['role']})")
    print(f"  Allowed models: {user_config['allowed_models']}")
    print(f"  Max tokens: {user_config['max_tokens']}")
    print(f"{'='*60}")

    # Authenticate user
    try:
        jwt_token, _ = RemoteIdentityProvider().login(username, user_config["password"])
        print(f"  [OK] Authenticated {username}")
    except Exception as e:
        print(f"  [ERROR] Failed to authenticate: {e}")
        return

    # Create user agent
    user = MACAWClient(
        user_name=username,
        iam_token=jwt_token,
        agent_type="user",
        app_name="financial-analyzer"
    )
    user.register()
    print(f"  [OK] Registered user agent: {user.agent_id}")

    # Bind user to service
    user_openai = openai_service.bind_to_user(user)
    print(f"  [OK] Bound user to OpenAI service")

    # Test 1: Allowed request (GPT-3.5)
    print(f"\n  Test 1: GPT-3.5 with 400 tokens")
    try:
        response = user_openai.chat.completions.create(
            model="gpt-3.5-turbo",
            max_tokens=400,
            messages=[{"role": "user", "content": "What is compound interest? Brief answer."}]
        )
        print(f"    [PASS] Response received: {response.choices[0].message.content[:50]}...")
    except Exception as e:
        print(f"    [FAIL] Unexpected error: {e}")

    # Test 2: GPT-4 (only bob and carol allowed)
    print(f"\n  Test 2: GPT-4 with 400 tokens")
    try:
        response = user_openai.chat.completions.create(
            model="gpt-4",
            max_tokens=400,
            messages=[{"role": "user", "content": "What is revenue growth? Brief answer."}]
        )
        if "gpt-4" in user_config["allowed_models"]:
            print(f"    [PASS] Response received (GPT-4 allowed for {username})")
        else:
            print(f"    [FAIL] Should have been blocked!")
    except Exception as e:
        if "gpt-4" not in user_config["allowed_models"]:
            print(f"    [PASS] Correctly blocked: {str(e)[:50]}...")
        else:
            print(f"    [FAIL] Should have been allowed: {e}")

    # Test 3: Exceeding token limit
    exceeded_tokens = user_config["max_tokens"] + 500
    print(f"\n  Test 3: GPT-3.5 with {exceeded_tokens} tokens (exceeds limit)")
    try:
        response = user_openai.chat.completions.create(
            model="gpt-3.5-turbo",
            max_tokens=exceeded_tokens,
            messages=[{"role": "user", "content": "Hello"}]
        )
        print(f"    [FAIL] Should have been blocked (exceeds max_tokens)!")
    except Exception as e:
        print(f"    [PASS] Correctly blocked: {str(e)[:50]}...")

    # Cleanup
    user_openai.unbind()
    print(f"\n  [OK] Unbound user from service")


def main():
    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("ERROR: Set OPENAI_API_KEY environment variable")
        print("  export OPENAI_API_KEY=sk-your-key-here")
        sys.exit(1)

    print("=" * 60)
    print("MACAW Role-Based AI Access Control Demo")
    print("=" * 60)

    # Create shared OpenAI service
    print("\n[Setup] Creating SecureOpenAI service...")
    openai_service = SecureOpenAI(app_name="financial-analyzer")
    print(f"  Service ID: {openai_service.server_id}")

    # Test each user
    for username, config in TEST_USERS.items():
        test_user_with_bind_to_user(openai_service, username, config)

    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)
    print("\nCheck the MACAW Console Logs tab to see policy decisions.")


if __name__ == "__main__":
    main()
