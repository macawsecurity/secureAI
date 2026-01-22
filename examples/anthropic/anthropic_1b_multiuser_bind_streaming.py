#!/usr/bin/env python3
"""
Example 1b-stream: Multi-user with Streaming (Anthropic)

Use this when: SaaS app with real-time streaming responses.
Policy checks happen BEFORE streaming starts.

NOTE: Claude uses messages.stream() context manager pattern,
not stream=True like OpenAI.

Prerequisites:
    - Identity provider setup (see setup/README.md)
    - Policies loaded for alice and bob (see policies/)

Run with:
    PYTHONPATH=/path/to/secureAI python anthropic_1b_multiuser_bind_streaming.py
"""

import os

from macaw_adapters.anthropic import SecureAnthropic
from macaw_client import MACAWClient, RemoteIdentityProvider


# Test configurations based on user policies
# Alice: Haiku only, max 500 tokens
# Bob: Haiku/Sonnet/Opus, max 2000 tokens
USER_TESTS = {
    "alice": {
        "password": "Alice123!",
        "policy_desc": "Claude Haiku only, max 500 tokens",
        "tests": [
            # (model, max_tokens, should_succeed)
            ("claude-3-haiku-20240307", 400, True),   # ALLOWED
            ("claude-opus-4-5-20251101", 400, False),  # BLOCKED - alice can't use Opus
        ]
    },
    "bob": {
        "password": "Bob@123!",
        "policy_desc": "Claude Haiku/Sonnet/Opus, max 2000 tokens",
        "tests": [
            ("claude-3-haiku-20240307", 400, True),   # ALLOWED
            ("claude-opus-4-5-20251101", 400, True),   # ALLOWED - bob CAN use Opus
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


def test_user(username: str, anthropic_service: SecureAnthropic):
    """Test a user with streaming bind_to_user pattern."""
    config = USER_TESTS[username]

    print(f"\n{'=' * 60}")
    print(f"Testing {username.upper()} via bind_to_user (STREAMING)")
    print(f"Policy: {config['policy_desc']}")
    print("=" * 60)

    # 1. Create user client with JWT
    user_client = create_user_client(username, config["password"])

    # 2. Bind user to service
    print(f"\n  Binding to service: {anthropic_service.server_id}")
    user_anthropic = anthropic_service.bind_to_user(user_client)

    # 3. Test with streaming
    print(f"\n  Running streaming tests:")
    for model, max_tokens, should_succeed in config["tests"]:
        expected = "SHOULD SUCCEED" if should_succeed else "SHOULD BE BLOCKED"
        print(f"\n  -> {model}, {max_tokens} tokens ({expected})")

        try:
            # Claude streaming uses context manager pattern
            with user_anthropic.messages.stream(
                model=model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "user", "content": "What is revenue growth? Brief answer."}
                ]
            ) as stream:
                if should_succeed:
                    print(f"     SUCCESS (as expected)")
                    print(f"     Streaming: ", end="")
                    collected = []
                    for text in stream.text_stream:
                        collected.append(text)
                        print(text, end="", flush=True)
                    print()  # newline
                    print(f"     Total chars: {len(''.join(collected))}")
                else:
                    # If we got here, policy didn't block - unexpected
                    for text in stream.text_stream:
                        pass  # consume stream
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
    user_anthropic.unbind()
    print(f"  is_bound: {user_anthropic.is_bound}")


def main():
    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY environment variable")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        return

    print("=" * 60)
    print("Example 1b-stream: Multi-user with Streaming (Anthropic)")
    print("=" * 60)
    print("\nStreaming Pattern: messages.stream() context manager")
    print("Policy enforcement: BEFORE first chunk is returned")

    # Create SINGLE service (shared across all users)
    print("\n--- Creating SecureAnthropic service ---")
    anthropic_service = SecureAnthropic(app_name="anthropic-service")
    print(f"Service registered: {anthropic_service.server_id}")
    print(f"Mode: {anthropic_service._mode}")

    # Test alice (restricted)
    try:
        test_user("alice", anthropic_service)
    except Exception as e:
        print(f"\nFailed to test alice: {e}")

    # Test bob (enhanced)
    try:
        test_user("bob", anthropic_service)
    except Exception as e:
        print(f"\nFailed to test bob: {e}")

    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()
