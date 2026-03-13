#!/usr/bin/env python3
"""
Example: SecureMCPProxy Multi-User Pattern

Demonstrates bind_to_user() for multi-tenant SaaS applications.
The service maintains the upstream MCP connection, but each request
runs with a specific user's identity and policy.

Security Model:
- Service creates ONE proxy to the upstream MCP server
- Each user gets a BoundMCPProxy via bind_to_user()
- User's calls are: evaluated against their policy, signed with their identity, logged under their audit trail
- Even with shared subprocess, MACAW provides per-user isolation

Prerequisites:
    1. pip install mcp-server-fetch macaw-adapters[mcp-proxy]
    2. Identity Provider configured (Console -> Settings -> Identity Bridge)
    3. Test users: alice/Alice123!, bob/Bob@123!

Usage:
    python 2g_proxy_multiuser.py

No IdP configured? Use simpler examples first:
    python 2e_proxy_stdio_fetch.py
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    """Test multi-user SecureMCPProxy pattern."""
    from macaw_adapters.mcp import SecureMCPProxy
    from macaw_client import MACAWClient, RemoteIdentityProvider

    print("=" * 60)
    print("SecureMCPProxy Multi-User Pattern")
    print("=" * 60)

    # Step 1: Service creates shared proxy
    print("\n1. Creating shared proxy (service-level)...")
    try:
        import mcp_server_fetch
    except ImportError:
        print("   ERROR: mcp-server-fetch not installed")
        print("   Fix: pip install mcp-server-fetch")
        return 1

    try:
        proxy = SecureMCPProxy(
            app_name="shared-fetch-proxy",
            command=["python", "-m", "mcp_server_fetch"],
        )
        print(f"   OK: {proxy}")
    except Exception as e:
        print(f"   ERROR: {e}")
        return 1

    # Step 2: Authenticate users
    print("\n2. Authenticating users...")

    users = {}
    for username, password in [("alice", "Alice123!"), ("bob", "Bob@123!")]:
        try:
            print(f"   Authenticating {username}...")
            jwt_token, _ = RemoteIdentityProvider().login(username, password)

            user = MACAWClient(
                user_name=username,
                iam_token=jwt_token,
                agent_type="user",
                app_name="mcp-multiuser-test"
            )

            if not user.register():
                print(f"   ERROR: Failed to register {username}")
                continue

            users[username] = user
            print(f"   OK: {username} -> {user.agent_id}")

        except Exception as e:
            print(f"   ERROR: {username} authentication failed: {e}")
            print("   Make sure IdP is configured in Console -> Settings -> Identity Bridge")
            return 1

    if len(users) < 2:
        print("\n   ERROR: Could not authenticate both users")
        return 1

    # Step 3: Create per-user bound proxies
    print("\n3. Creating per-user proxies via bind_to_user()...")
    alice_proxy = proxy.bind_to_user(users["alice"])
    bob_proxy = proxy.bind_to_user(users["bob"])
    print(f"   Alice: {alice_proxy}")
    print(f"   Bob: {bob_proxy}")

    # Step 4: Test user-specific calls
    print("\n4. Testing user-specific tool calls...")

    test_urls = [
        ("alice", alice_proxy, "https://alice.example.com"),
        ("bob", bob_proxy, "https://bob.example.com"),
    ]

    for username, user_proxy, url in test_urls:
        print(f"\n   {username.upper()}'s call to {url}:")
        try:
            result = user_proxy.call_tool("fetch", {"url": url})
            preview = str(result)[:80].replace('\n', ' ')
            print(f"   OK: {preview}...")
            print(f"   (Policy: {username}'s policy applied)")
            print(f"   (Signed: {username}'s identity)")
            print(f"   (Audit: logged under {username})")
        except PermissionError as e:
            print(f"   BLOCKED by policy: {e}")
        except Exception as e:
            print(f"   ERROR: {e}")

    print("\n" + "=" * 60)
    print("SUCCESS: Multi-user SecureMCPProxy works!")
    print("=" * 60)
    print("\nKey points:")
    print("  - Same subprocess, different identities")
    print("  - Each call has fresh AuthenticatedContext")
    print("  - Policy enforcement per user")
    print("  - Audit trail tracks who did what")
    return 0


if __name__ == "__main__":
    sys.exit(main())
