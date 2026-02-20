#!/usr/bin/env python3
"""
anthropic_1c_a2a_invoke.py - Agent-to-Agent invocation with invoke_tool

Demonstrates explicit tool invocation for agent systems and cross-service calls.
Use when you need fine-grained control over routing and tool invocation.

Prerequisites:
    - MACAW SDK installed (pip install macaw-client macaw-adapters)
    - ANTHROPIC_API_KEY environment variable
    - Identity Provider configured (Console -> Settings -> Identity Bridge)
    - Test users: alice/Alice123!

Run:
    export ANTHROPIC_API_KEY=sk-ant-...
    python anthropic_1c_a2a_invoke.py

No IdP configured? Run simpler example first:
    python anthropic_1a_dropin_simple.py
"""

import os
import sys

from macaw_adapters.anthropic import SecureAnthropic
from macaw_client import MACAWClient, RemoteIdentityProvider


def main():
    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Set ANTHROPIC_API_KEY environment variable")
        print("  export ANTHROPIC_API_KEY=sk-ant-...")
        return

    print("=" * 60)
    print("Example 1c: A2A with invoke_tool (Anthropic)")
    print("=" * 60)
    print("\nPath: invoke_tool (explicit A2A control)")
    print("Use when: Agent systems, explicit control, cross-service calls")
    print("\nArchitecture:")
    print("  - SecureAnthropic service registers tools")
    print("  - User agent calls invoke_tool() directly")
    print("  - Must know MAPL tool name: tool:<app>/generate")
    print("  - Returns raw dict (not SDK types)")

    # 1. Create Anthropic service
    print("\n--- Creating SecureAnthropic service ---")
    anthropic_service = SecureAnthropic(app_name="anthropic-service")
    print(f"Service registered: {anthropic_service.server_id}")
    print(f"Tools registered:")
    for tool_name in anthropic_service.tools.keys():
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
    print(f"  Tool name: tool:{anthropic_service.app_name}/generate")
    print(f"  Target: {anthropic_service.server_id}")

    result = user.invoke_tool(
        tool_name=f"tool:{anthropic_service.app_name}/generate",
        parameters={
            "model": "claude-3-haiku-20240307",
            "max_tokens": 100,
            "messages": [
                {"role": "user", "content": "What is compound interest? Brief answer."}
            ]
        },
        target_agent=anthropic_service.server_id
    )

    # Result is raw dict - you handle parsing
    if isinstance(result, dict):
        if "error" in result:
            print(f"  Error: {result['error']}")
        elif "content" in result:
            # Claude response format
            content = result["content"][0]["text"]
            print(f"  Success!")
            print(f"  Model: {result.get('model')}")
            print(f"  Response: {content[:80]}...")
        else:
            print(f"  Unexpected result: {result}")

    # 4. Test policy enforcement
    print("\n--- Test 2: Policy enforcement (Opus blocked for alice) ---")
    try:
        result = user.invoke_tool(
            tool_name=f"tool:{anthropic_service.app_name}/generate",
            parameters={
                "model": "claude-opus-4-5-20251101",  # Alice can't use Opus!
                "max_tokens": 100,
                "messages": [{"role": "user", "content": "Hello"}]
            },
            target_agent=anthropic_service.server_id
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
    print(f"  Known service: {anthropic_service.server_id}")
    print(f"  Tool pattern: tool:<app_name>/generate")

    print("\n" + "=" * 60)
    print("Example complete!")
    print("=" * 60)
    print("\nKey differences from bind_to_user:")
    print("  - Must know MAPL tool names (tool:xxx/generate)")
    print("  - Must know target agent server_id")
    print("  - Returns raw dict (not Message)")
    print("  - More control, but more responsibility")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        err = str(e)
        print("\n" + "=" * 60)
        if "ANTHROPIC_API_KEY" in err or "api_key" in err.lower():
            print("ERROR: Anthropic API key not configured")
            print("Fix: export ANTHROPIC_API_KEY=sk-ant-...")
        elif "Local provider does not support" in err:
            print("ERROR: Identity Provider not configured")
            print("Fix: Console -> Settings -> Identity Bridge")
            print("\nOr run simpler example first:")
            print("  python anthropic_1a_dropin_simple.py")
        else:
            print(f"ERROR: {e}")
        print("=" * 60)
        sys.exit(1)
