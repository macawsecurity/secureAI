#!/usr/bin/env python3
"""
openai_1d_invocation_patterns.py - Compare invoke_tool vs bind_to_user

Compares two ways to invoke SecureOpenAI with the same security guarantees:

PATH 1: Direct invoke_tool
  - Explicit A2A (agent-to-agent) control
  - Must know MAPL tool name: tool:<app>/generate
  - Returns raw dict
  - Use when: Agent systems, cross-service calls, custom routing

PATH 2: bind_to_user wrapper
  - OpenAI-compatible API (chat.completions.create)
  - Familiar SDK experience
  - Internally calls invoke_tool
  - Use when: Drop-in replacement, developer ergonomics

Both paths enforce per-user policies and propagate JWT identity.

Prerequisites:
    - MACAW SDK installed (pip install macaw-client macaw-adapters)
    - OPENAI_API_KEY environment variable
    - Identity Provider configured (Console -> Settings -> Identity Bridge)
    - Test users: alice/Alice123!, bob/Bob@123!

Run:
    export OPENAI_API_KEY=sk-...
    python openai_1d_invocation_patterns.py

No IdP configured? Run simpler example first:
    python openai_1a_dropin_simple.py
"""

import os
import sys

from macaw_adapters.openai import SecureOpenAI
from macaw_client import MACAWClient, RemoteIdentityProvider


# User-specific test configurations based on their policies
# Alice: GPT-3.5 only, max 500 tokens
# Bob: GPT-3.5/4, max 2000 tokens
USER_TESTS = {
    "alice": {
        "password": "Alice123!",
        "policy_desc": "gpt-3.5-turbo only, max_tokens <= 500",
        "tests": [
            # (model, max_tokens, query, should_succeed)
            ("gpt-3.5-turbo", 400, "What is revenue growth?", True),          # ALLOWED
            ("gpt-4", 400, "What is revenue growth?", False),                  # BLOCKED - wrong model
            ("gpt-3.5-turbo", 600, "What is compound interest?", False),       # BLOCKED - exceeds max_tokens
        ]
    },
    "bob": {
        "password": "Bob@123!",
        "policy_desc": "gpt-3.5-turbo/gpt-4, max_tokens <= 2000",
        "tests": [
            # (model, max_tokens, query, should_succeed)
            ("gpt-3.5-turbo", 400, "What is revenue growth?", True),          # ALLOWED
            ("gpt-4", 400, "What is market cap?", True),                       # ALLOWED - Bob CAN use gpt-4
            ("gpt-3.5-turbo", 600, "What is compound interest?", True),        # ALLOWED - Bob's limit is 2000
            ("gpt-4", 2500, "Deep financial analysis", False),                 # BLOCKED - exceeds max_tokens
        ]
    }
}


def test_user_path1(username: str, openai_service: SecureOpenAI):
    """
    PATH 1: Direct invoke_tool (explicit A2A control).

    invoke_tool auto-creates authenticated prompts based on registry lookup.
    """
    print(f"\n{'='*60}")
    print(f"PATH 1: {username.upper()} via invoke_tool")
    print("="*60)

    user_config = USER_TESTS[username]

    # 1. Get JWT
    print(f"1. Authenticating...")
    jwt_token, _ = RemoteIdentityProvider().login(username, user_config["password"])
    print("   OK Got JWT token")

    # 2. Create user agent with JWT
    print("2. Creating user agent...")
    user = MACAWClient(
        user_name=username,
        iam_token=jwt_token,  # Converted to embedded_context automatically!
        agent_type="user",
        app_name="financial-analyzer"
    )

    if not user.register():
        print("   FAIL Failed to create user agent")
        return None
    print(f"   OK User agent: {user.agent_id}")

    # 3. Test with invoke_tool (auto-creates authenticated prompts!)
    tests = user_config["tests"]

    print(f"\n3. Testing via invoke_tool to service {openai_service.server_id}:")
    print("   (invoke_tool will auto-create authenticated prompts for 'messages')")
    print(f"   Policy: {username} -> {user_config['policy_desc']}")

    for model, max_tokens, query, should_succeed in tests:
        expected = "SHOULD SUCCEED" if should_succeed else "SHOULD BE BLOCKED"
        print(f"\n   -> {model} with {max_tokens} tokens ({expected})")

        try:
            # A2A call to single service agent
            # invoke_tool auto-creates authenticated prompts!
            result = user.invoke_tool(
                tool_name=f"tool:{openai_service.app_name}/generate",
                parameters={
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": "You are a financial analyst."},
                        {"role": "user", "content": query}
                    ]
                },
                target_agent=openai_service.server_id
            )

            # Check if we got a valid response
            if isinstance(result, dict):
                if "error" in result:
                    if should_succeed:
                        print(f"     FAIL UNEXPECTED FAILURE: {result['error']}")
                    else:
                        print(f"     PASS CORRECTLY BLOCKED: {result['error'][:60]}...")
                elif "choices" in result:
                    if should_succeed:
                        print(f"     PASS SUCCESS (as expected)")
                        print(f"       Model: {result.get('model')}")
                        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                        print(f"       Response: {content[:80]}...")
                    else:
                        print(f"     FAIL UNEXPECTED SUCCESS - should have been blocked!")
                else:
                    print(f"     FAIL Unexpected response: {result}")
            else:
                print(f"     FAIL Invalid response type: {type(result)}")

        except Exception as e:
            error = str(e)
            is_policy_block = ("not in allowed" in error or "not permitted" in error or
                               "policy" in error.lower() or "max_tokens" in error or
                               "model" in error or "blocked" in error.lower())
            if is_policy_block:
                if should_succeed:
                    print(f"     FAIL UNEXPECTED BLOCK: {error}")
                else:
                    print(f"     PASS CORRECTLY BLOCKED by policy")
            else:
                print(f"     FAIL Error: {error}")

    return user


def test_user_path2(username: str, openai_service: SecureOpenAI):
    """
    PATH 2: bind_to_user wrapper (OpenAI-compatible API).

    Same underlying invoke_tool, but wrapped in OpenAI-compatible API.
    """
    print(f"\n{'='*60}")
    print(f"PATH 2: {username.upper()} via bind_to_user")
    print("="*60)

    user_config = USER_TESTS[username]

    # 1. Get JWT
    print(f"1. Authenticating...")
    jwt_token, _ = RemoteIdentityProvider().login(username, user_config["password"])
    print("   OK Got JWT token")

    # 2. Create user agent with JWT
    print("2. Creating user agent...")
    user = MACAWClient(
        user_name=username,
        iam_token=jwt_token,
        agent_type="user",
        app_name="financial-analyzer"
    )

    if not user.register():
        print("   FAIL Failed to create user agent")
        return
    print(f"   OK User agent: {user.agent_id}")

    # 3. Bind user to service
    print("3. Binding user to SecureOpenAI service...")
    user_openai = openai_service.bind_to_user(user)
    print(f"   OK Bound to: {openai_service.server_id}")

    # 4. Test with OpenAI-style API
    tests = user_config["tests"]

    print(f"\n4. Testing via bind_to_user wrapper:")
    print("   (internally calls invoke_tool which auto-creates auth prompts)")
    print(f"   Policy: {username} -> {user_config['policy_desc']}")

    for model, max_tokens, query, should_succeed in tests:
        expected = "SHOULD SUCCEED" if should_succeed else "SHOULD BE BLOCKED"
        print(f"\n   -> {model} with {max_tokens} tokens ({expected})")

        try:
            response = user_openai.chat.completions.create(
                model=model,
                max_tokens=max_tokens,
                messages=[
                    {"role": "system", "content": "You are a financial analyst."},
                    {"role": "user", "content": query}
                ]
            )

            if should_succeed:
                print(f"     PASS SUCCESS (as expected)")
                print(f"       Model: {response.model}")
                print(f"       Response: {response.choices[0].message.content[:80]}...")
            else:
                print(f"     FAIL UNEXPECTED SUCCESS - should have been blocked!")

        except Exception as e:
            error = str(e)
            is_policy_block = ("not in allowed" in error or "not permitted" in error or
                               "policy" in error.lower() or "max_tokens" in error or
                               "model" in error or "blocked" in error.lower())
            if is_policy_block:
                if should_succeed:
                    print(f"     FAIL UNEXPECTED BLOCK: {error}")
                else:
                    print(f"     PASS CORRECTLY BLOCKED by policy")
            else:
                print(f"     FAIL Error: {error}")

    # 5. Demonstrate unbind
    print(f"\n5. Testing unbind()...")
    print(f"   is_bound before: {user_openai.is_bound}")
    user_openai.unbind()
    print(f"   is_bound after: {user_openai.is_bound}")
    try:
        user_openai.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": "test"}])
        print(f"     FAIL Call should have failed after unbind!")
    except RuntimeError as e:
        print(f"     PASS Correctly rejected: {str(e)[:50]}...")


def main():
    """Compare both invocation patterns with multi-user policy enforcement."""
    print("\n" + "="*70)
    print("Invocation Patterns Demo + MACAW Policy Enforcement")
    print("="*70)
    print("\nArchitecture:")
    print("  - Single SecureOpenAI service agent (created once)")
    print("  - User agents with JWT -> embedded_context (automatic)")
    print("  - A2A calls: User -> SecureOpenAI service")
    print("  - Policy enforcement at ToolAgent PEP level")
    print("  - Authenticated prompts auto-created by invoke_tool")

    print("\nTwo invocation patterns tested:")
    print("  PATH 1: Direct invoke_tool (explicit A2A control)")
    print("  PATH 2: bind_to_user wrapper (OpenAI-compatible API)")

    print("\nExpected policies (enforced by ToolAgent PEP):")
    print("  - Alice: GPT-3.5 only, max 500 tokens")
    print("  - Bob: GPT-3.5/4, max 2000 tokens")

    if not os.environ.get("OPENAI_API_KEY"):
        print("\nWARNING: No OPENAI_API_KEY - demo will fail")
        print("   Set with: export OPENAI_API_KEY=sk-...")
        return

    # Create SINGLE SecureOpenAI service (ONCE!)
    print("\n" + "="*70)
    print("Creating single SecureOpenAI service agent...")
    print("="*70)

    openai_service = SecureOpenAI(
        api_key=os.environ.get("OPENAI_API_KEY"),
        app_name="openai-service"
    )

    print(f"OK SecureOpenAI service: {openai_service.server_id}")

    # Test Alice with PATH 1 (invoke_tool)
    try:
        test_user_path1("alice", openai_service)
    except Exception as e:
        print(f"\nFAIL Failed PATH 1 for alice: {e}")

    # Test Alice with PATH 2 (bind_to_user)
    try:
        test_user_path2("alice", openai_service)
    except Exception as e:
        print(f"\nFAIL Failed PATH 2 for alice: {e}")

    # Test Bob with PATH 1 (invoke_tool)
    try:
        test_user_path1("bob", openai_service)
    except Exception as e:
        print(f"\nFAIL Failed PATH 1 for bob: {e}")

    # Test Bob with PATH 2 (bind_to_user)
    try:
        test_user_path2("bob", openai_service)
    except Exception as e:
        print(f"\nFAIL Failed PATH 2 for bob: {e}")

    # Summary
    print("\n" + "="*70)
    print("Demo complete!")
    print("="*70)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err = str(e)
        print("\n" + "=" * 60)
        if "OPENAI_API_KEY" in err or "api_key" in err.lower():
            print("ERROR: OpenAI API key not configured")
            print("Fix: export OPENAI_API_KEY=sk-...")
        elif "Local provider does not support" in err:
            print("ERROR: Identity Provider not configured")
            print("Fix: Console -> Settings -> Identity Bridge")
            print("\nOr run simpler example first:")
            print("  python openai_1a_dropin_simple.py")
        else:
            print(f"ERROR: {e}")
        print("=" * 60)
        sys.exit(1)
