#!/usr/bin/env python3
"""
Example 1b: Multi-user with bind_to_user (OpenAI)

Use this when: SaaS app, different users need different permissions.
Each user's JWT identity flows through for policy evaluation.

Prerequisites:
    - Identity provider setup (see setup/README.md)
    - Policies loaded for alice and bob (see policies/)

Run with:
    PYTHONPATH=/path/to/secureAI python openai_1b_multiuser_bind.py
"""

import os

from macaw_adapters.openai import SecureOpenAI
from macaw_client import MACAWClient, RemoteIdentityProvider


# Test configurations based on user policies
# Alice: GPT-3.5 only, max 500 tokens
# Bob: GPT-3.5/4, max 2000 tokens
USER_TESTS = {
    "alice": {
        "password": "Alice123!",
        "policy_desc": "GPT-3.5 only, max 500 tokens",
        "tests": [
            # (model, max_tokens, should_succeed)
            ("gpt-3.5-turbo", 400, True),   # ALLOWED - correct model, within limit
            ("gpt-4", 400, False),           # BLOCKED - alice can't use GPT-4
            ("gpt-3.5-turbo", 600, False),   # BLOCKED - exceeds max_tokens
        ]
    },
    "bob": {
        "password": "Bob@123!",
        "policy_desc": "GPT-3.5/4, max 2000 tokens",
        "tests": [
            ("gpt-3.5-turbo", 400, True),   # ALLOWED
            ("gpt-4", 400, True),            # ALLOWED - bob CAN use GPT-4
            ("gpt-3.5-turbo", 600, True),   # ALLOWED - within bob's 2000 limit
            ("gpt-4", 2500, False),          # BLOCKED - exceeds max_tokens
        ]
    }
}


def create_user_client(username: str, password: str) -> MACAWClient:
    """Create authenticated user client."""
    print(f"  Authenticating {username}...")
    jwt_token, _ = RemoteIdentityProvider().login(username, password)

    user = MACAWClient(
        user_name=username,
        iam_token=jwt_token,
        agent_type="user",
        app_name="financial-app"
    )

    if not user.register():
        raise RuntimeError(f"Failed to register user {username}")

    print(f"  User agent: {user.agent_id}")
    return user


def test_user(username: str, openai_service: SecureOpenAI):
    """Test a user with bind_to_user pattern."""
    config = USER_TESTS[username]

    print(f"\n{'=' * 60}")
    print(f"Testing {username.upper()} via bind_to_user")
    print(f"Policy: {config['policy_desc']}")
    print("=" * 60)

    # 1. Create user client with JWT
    user_client = create_user_client(username, config["password"])

    # 2. Bind user to service
    print(f"\n  Binding to service: {openai_service.server_id}")
    user_openai = openai_service.bind_to_user(user_client)

    # 3. Test with different parameters
    print(f"\n  Running tests:")
    for model, max_tokens, should_succeed in config["tests"]:
        expected = "SHOULD SUCCEED" if should_succeed else "SHOULD BE BLOCKED"
        print(f"\n  -> {model}, {max_tokens} tokens ({expected})")

        try:
            response = user_openai.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": "You are a financial analyst."},
                    {"role": "user", "content": "What is revenue growth? Brief answer."}
                ],
                stream=True
            )

            if should_succeed:
                print(f"     SUCCESS (as expected)")
                # Collect streaming chunks
                collected_content = []
                chunk_count = 0
                for chunk in response:
                    chunk_count += 1
                    if chunk.choices and chunk.choices[0].delta.content:
                        collected_content.append(chunk.choices[0].delta.content)
                full_content = "".join(collected_content)
                print(f"     Chunks received: {chunk_count}")
                print(f"     Response: {full_content[:60]}...")
            else:
                print(f"     UNEXPECTED SUCCESS - should have been blocked!")

        except Exception as e:
            error = str(e)
            is_policy_block = any(word in error.lower() for word in
                                  ["not in allowed", "not permitted", "policy",
                                   "max_tokens", "model", "blocked", "denied"])
            if is_policy_block:
                if should_succeed:
                    print(f"     UNEXPECTED BLOCK: {error[:60]}...")
                else:
                    print(f"     CORRECTLY BLOCKED by policy")
            else:
                print(f"     ERROR: {error[:60]}...")

    # 4. Cleanup
    print(f"\n  Unbinding user...")
    user_openai.unbind()
    print(f"  is_bound: {user_openai.is_bound}")


def main():
    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY environment variable")
        print("  export OPENAI_API_KEY=sk-...")
        return

    print("=" * 60)
    print("Example 1b: Multi-user with bind_to_user (OpenAI)")
    print("=" * 60)
    print("\nPath: bind_to_user (per-user identity)")
    print("Use when: SaaS app, different users need different permissions")
    print("\nArchitecture:")
    print("  - Single SecureOpenAI service (shared)")
    print("  - Per-user MACAWClient with JWT identity")
    print("  - bind_to_user() connects user to service")
    print("  - User's identity flows through for policy evaluation")

    # Create SINGLE service (shared across all users)
    print("\n--- Creating SecureOpenAI service ---")
    openai_service = SecureOpenAI(app_name="openai-service")
    print(f"Service registered: {openai_service.server_id}")
    print(f"Mode: {openai_service._mode}")

    # Test alice (restricted)
    try:
        test_user("alice", openai_service)
    except Exception as e:
        print(f"\nFailed to test alice: {e}")

    # Test bob (enhanced)
    try:
        test_user("bob", openai_service)
    except Exception as e:
        print(f"\nFailed to test bob: {e}")

    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
