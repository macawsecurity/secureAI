#!/usr/bin/env python3
"""
openai_1c_a2a_invoke.py - Agent-to-Agent invocation with invoke_tool

Demonstrates explicit tool invocation for agent systems and cross-service calls.
Use when you need fine-grained control over routing and tool invocation.

Prerequisites:
    - MACAW SDK installed (pip install macaw-client macaw-adapters)
    - OPENAI_API_KEY environment variable
    - Identity Provider configured (Console -> Settings -> Identity Bridge)
    - Test users: alice/Alice123!

Run:
    export OPENAI_API_KEY=sk-...
    python openai_1c_a2a_invoke.py

No IdP configured? Run simpler example first:
    python openai_1a_dropin_simple.py
"""

import os
import sys

from macaw_adapters.openai import SecureOpenAI
from macaw_client import MACAWClient, RemoteIdentityProvider


def main():
    # Check for API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("Set OPENAI_API_KEY environment variable")
        print("  export OPENAI_API_KEY=sk-...")
        return

    print("=" * 60)
    print("Example 1c: A2A with invoke_tool (OpenAI)")
    print("=" * 60)
    print("\nPath: invoke_tool (explicit A2A control)")
    print("Use when: Agent systems, explicit control, cross-service calls")
    print("\nArchitecture:")
    print("  - SecureOpenAI service registers tools")
    print("  - User agent calls invoke_tool() directly")
    print("  - Must know MAPL tool name: tool:<app>/generate")
    print("  - Returns raw dict (not SDK types)")

    # 1. Create OpenAI service
    print("\n--- Creating SecureOpenAI service ---")
    openai_service = SecureOpenAI(app_name="openai-service")
    print(f"Service registered: {openai_service.server_id}")
    print(f"Tools registered:")
    for tool_name in openai_service.tools.keys():
        print(f"  - {tool_name}")

    # 2. Create user agent with JWT
    print("\n--- Creating user agent ---")
    print("  Authenticating alice...")
    jwt_token, _ = RemoteIdentityProvider().login("alice", "Alice123!")

    user = MACAWClient(
        user_name="alice",
        iam_token=jwt_token,
        agent_type="user",
        app_name="my-agent"
    )

    if not user.register():
        print("  Failed to register user agent")
        return

    print(f"  User agent: {user.agent_id}")

    # 3. Explicit invoke_tool
    print("\n--- Test 1: Direct invoke_tool ---")
    print(f"  Tool name: tool:{openai_service.app_name}/generate")
    print(f"  Target: {openai_service.server_id}")

    result = user.invoke_tool(
        tool_name=f"tool:{openai_service.app_name}/generate",
        parameters={
            "model": "gpt-3.5-turbo",
            "max_tokens": 100,
            "messages": [
                {"role": "system", "content": "You are a financial analyst."},
                {"role": "user", "content": "What is compound interest? Brief answer."}
            ]
        },
        target_agent=openai_service.server_id
    )

    # Result is raw dict - you handle parsing
    if isinstance(result, dict):
        if "error" in result:
            print(f"  Error: {result['error']}")
        elif "choices" in result:
            content = result["choices"][0]["message"]["content"]
            print(f"  Success!")
            print(f"  Model: {result.get('model')}")
            print(f"  Response: {content[:80]}...")
        else:
            print(f"  Unexpected result: {result}")

    # 4. Test policy enforcement
    print("\n--- Test 2: Policy enforcement (GPT-4 blocked for alice) ---")
    try:
        result = user.invoke_tool(
            tool_name=f"tool:{openai_service.app_name}/generate",
            parameters={
                "model": "gpt-4",  # Alice can't use GPT-4!
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "Hello"}]
            },
            target_agent=openai_service.server_id
        )

        if isinstance(result, dict) and "error" in result:
            print(f"  Correctly blocked: {result['error'][:60]}...")
        else:
            print(f"  Unexpected - should have been blocked!")
    except Exception as e:
        print(f"  Correctly blocked: {str(e)[:60]}...")

    # 5. Service discovery (optional advanced feature)
    print("\n--- Service Discovery ---")
    print("  (Agents can discover services dynamically via registry)")
    print(f"  Known service: {openai_service.server_id}")
    print(f"  Tool pattern: tool:<app_name>/generate")

    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)
    print("\nKey differences from bind_to_user:")
    print("  - Must know MAPL tool names (tool:xxx/generate)")
    print("  - Must know target agent server_id")
    print("  - Returns raw dict (not ChatCompletion)")
    print("  - More control, but more responsibility")


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
