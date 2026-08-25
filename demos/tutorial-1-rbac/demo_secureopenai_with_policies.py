#!/usr/bin/env python3
"""
SecureOpenAI Demo with MACAW Policies

This demo shows the efficient architecture:
1. Single SecureOpenAI service agent (created once)
2. User agents with JWT delegation (automatic embedded_context)
3. A2A calls from users to service
4. Policy enforcement at ToolAgent PEP level
"""

import os
import sys

from macaw_adapters.openai import SecureOpenAI
from macaw_client import MACAWClient, RemoteIdentityProvider


# User credentials
USERS = {
    "alice": "Alice123!",
    "bob": "Bob@123!",
    "carol": "Carol123!",
}


def test_user(username: str, password: str, openai_service: SecureOpenAI):
    """Test what a user can access."""
    print(f"\n{'='*60}")
    print(f"Testing {username.upper()}")
    print("="*60)

    # 1. Get JWT
    print(f"1. Authenticating...")
    jwt_token, _ = RemoteIdentityProvider().login(username, password)
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
        return
    print(f"   OK User agent: {user.agent_id}")

    # 3. Test different models and tokens
    tests = [
        ("gpt-3.5-turbo", 400, "Quick analysis"),
        ("gpt-3.5-turbo", 600, "Detailed analysis"),
        ("gpt-4", 1500, "Deep analysis"),
    ]

    print(f"\n3. Testing OpenAI access via A2A to service {openai_service.server_id}:")
    for model, max_tokens, query in tests:
        print(f"\n   -> {model} with {max_tokens} tokens")

        try:
            # A2A call to single service agent
            result = user.invoke_tool(
                tool_name="tool:openai-service/generate",  # MAPL-compliant resource name
                parameters={
                    "model": model,
                    "max_tokens": max_tokens,
                    "messages": [
                        {"role": "system", "content": "You are a financial analyst."},
                        {"role": "user", "content": query}
                    ]
                },
                target_agent=openai_service.server_id  # Same service for all users!
            )

            # Check if we got a valid response
            if isinstance(result, dict):
                if "error" in result:
                    print(f"     FAIL Failed: {result['error']}")
                elif "choices" in result:
                    print(f"     PASS SUCCESS")
                    print(f"       Model: {result.get('model')}")
                    content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
                    print(f"       Response: {content[:80]}...")
                else:
                    print(f"     FAIL Unexpected response: {result}")
            else:
                print(f"     FAIL Invalid response type: {type(result)}")

        except Exception as e:
            error = str(e)
            if "not in allowed" in error or "not permitted" in error or "policy" in error.lower():
                print(f"     BLOCKED by policy")
            elif "max_tokens" in error:
                print(f"     BLOCKED: Exceeds token limit")
            elif "model" in error:
                print(f"     BLOCKED: Model not allowed")
            else:
                print(f"     Error: {error}")


def main():
    """Test all users."""
    print("\n" + "="*70)
    print("SecureOpenAI + MACAW Policy Demo")
    print("="*70)
    print("\nArchitecture:")
    print("  - Single SecureOpenAI service agent (created once)")
    print("  - User agents with JWT -> embedded_context (automatic)")
    print("  - A2A calls: User -> SecureOpenAI service")
    print("  - Policy enforcement at ToolAgent PEP level")

    print("\nExpected results:")
    print("  - Alice: GPT-3.5 only, max 500 tokens")
    print("  - Bob: GPT-3.5/4, max 2000 tokens")
    print("  - Carol: All models, max 4000 tokens")

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

    # Test each user with same service
    for username, password in USERS.items():
        try:
            test_user(username, password, openai_service)
        except Exception as e:
            print(f"\nFAIL Failed to test {username}: {e}")

    print("\n" + "="*70)
    print("Demo complete!")
    print("="*70)


if __name__ == "__main__":
    main()
