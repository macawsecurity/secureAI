#!/usr/bin/env python3
"""
1b_grant_researcher.py - Reusable Capability Grant (Researcher)

A researcher needs admin approval to use web_search.
- First invocation: BLOCKS until admin approves
- Second+ invocations: IMMEDIATE (reuses existing approval)

The key difference from Example 1a is: one_time=False

This demonstrates:
- Reusable grants: approve once, use many times
- time_to_live: how long the grant lasts
- attestation_accessed audit event on reuse

NOTE: This example requires interactive approval and is not suitable
for automated test harnesses.

Prerequisites:
    - MACAW SDK installed (pip install macaw-client macaw-adapters)
    - Identity Provider configured (Console -> Settings -> Identity Bridge)
    - Test users: alice/Alice123!, bob/Bob@123! (bob needs admin role)

Run:
    # Terminal 1: Run researcher request (will block waiting)
    python 1b_grant_researcher.py

    # Terminal 2: Run admin approval
    python 1b_grant_admin.py
"""

import json
import time

from macaw_client import MACAWClient, RemoteIdentityProvider


def web_search_handler(params):
    """Simulate web search."""
    query = params.get('query', '')
    print(f"\n  [TOOL] web_search invoked!")
    print(f"  [TOOL] Query: {query}")

    # Simulate search results
    result = {
        "status": "success",
        "query": query,
        "results": [
            {"title": f"Result 1 for '{query}'", "url": "https://example.com/1"},
            {"title": f"Result 2 for '{query}'", "url": "https://example.com/2"},
        ]
    }
    print(f"  [TOOL] Returning {len(result['results'])} results")
    return result


def main():
    print("=" * 60)
    print("Example 1b: Reusable Capability Grant - Researcher")
    print("=" * 60)

    # Step 1: Create Search Service
    print("\n[Step 1] Creating Search Service...")

    try:
        search_service = MACAWClient(
            app_name="search",
            agent_type="service",
            tools={
                "tool:search/web_search": {
                    "handler": web_search_handler,
                    "description": "Search the web for information"
                }
            }
        )

        if not search_service.register():
            print("  ERROR: Failed to register Search Service")
            return 1

        print(f"  Service ID: {search_service.agent_id}")
        print(f"  Provides: tool:search/web_search")

    except Exception as e:
        print(f"  ERROR: {e}")
        return 1

    # Step 2: Authenticate as researcher (using alice credentials)
    print("\n[Step 2] Authenticating as researcher...")
    try:
        jwt_token, _ = RemoteIdentityProvider().login("alice", "Alice123!")
        print("  Got JWT token")
    except Exception as e:
        print(f"  ERROR: Failed to authenticate: {e}")
        search_service.unregister()
        return 1

    # Step 3: Create researcher agent with REUSABLE attestation (one_time=False)
    print("\n[Step 3] Creating researcher agent...")
    try:
        researcher = MACAWClient(
            user_name="researcher",
            iam_token=jwt_token,
            agent_type="user",
            app_name="research-app",
            intent_policy={
                "resources": ["tool:search/web_search"],
                # Attestation always required for this tool
                "attestations": ["capability:web_search"],
                # Attestation metadata - REUSABLE
                "constraints": {
                    "attestations": {
                        "capability:web_search": {
                            "approval_criteria": "role:admin",
                            "timeout": 300,       # 5 min to approve
                            "one_time": False,    # KEY: Reusable!
                            "time_to_live": 3600  # Valid for 1 hour (or None for forever)
                        }
                    }
                }
            }
        )

        if not researcher.register():
            print("  ERROR: Failed to register researcher agent")
            search_service.unregister()
            return 1

        print(f"  Agent ID: {researcher.agent_id}")
        print(f"  one_time=False (REUSABLE capability)")

    except Exception as e:
        print(f"  ERROR: {e}")
        search_service.unregister()
        return 1

    # Step 4: First invocation - should BLOCK for approval
    print("\n" + "=" * 60)
    print("FIRST INVOCATION - Will block for admin approval")
    print("=" * 60)
    print("\n  >>> Run 1b_grant_admin.py in another terminal <<<")
    print("-" * 60)

    start_time = time.time()
    try:
        result = researcher.invoke_tool(
            tool_name="tool:search/web_search",
            target_agent=search_service.agent_id,
            parameters={"query": "MACAW security framework"}
        )
        elapsed = time.time() - start_time
        print(f"\n  FIRST SEARCH COMPLETED! (took {elapsed:.1f}s)")
        print(f"  Result: {json.dumps(result, indent=2)}")

    except Exception as e:
        print(f"\n  ERROR on first invocation: {e}")
        researcher.unregister()
        search_service.unregister()
        return 1

    # Step 5: Second invocation - should be IMMEDIATE (no blocking!)
    print("\n" + "=" * 60)
    print("SECOND INVOCATION - Should be IMMEDIATE (reusing approval)")
    print("=" * 60)

    start_time = time.time()
    try:
        result = researcher.invoke_tool(
            tool_name="tool:search/web_search",
            target_agent=search_service.agent_id,
            parameters={"query": "AI agent governance"}
        )
        elapsed = time.time() - start_time
        print(f"\n  SECOND SEARCH COMPLETED! (took {elapsed:.1f}s)")
        if elapsed < 2.0:
            print("  *** REUSED EXISTING APPROVAL - NO BLOCKING! ***")
        print(f"  Result: {json.dumps(result, indent=2)}")

    except Exception as e:
        print(f"\n  ERROR on second invocation: {e}")

    # Step 6: Third invocation - also immediate
    print("\n" + "=" * 60)
    print("THIRD INVOCATION - Also immediate")
    print("=" * 60)

    start_time = time.time()
    try:
        result = researcher.invoke_tool(
            tool_name="tool:search/web_search",
            target_agent=search_service.agent_id,
            parameters={"query": "enterprise AI security"}
        )
        elapsed = time.time() - start_time
        print(f"\n  THIRD SEARCH COMPLETED! (took {elapsed:.1f}s)")
        if elapsed < 2.0:
            print("  *** REUSED EXISTING APPROVAL - NO BLOCKING! ***")

    except Exception as e:
        print(f"\n  ERROR on third invocation: {e}")

    # Cleanup
    print("\n[Cleanup] Unregistering agents...")
    researcher.unregister()
    search_service.unregister()

    print("\n" + "=" * 60)
    print("Example 1b Complete!")
    print("First invocation required approval, subsequent were immediate.")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    import sys
    try:
        sys.exit(main())
    except Exception as e:
        err = str(e)
        print("\n" + "=" * 60)
        if "Local provider does not support" in err:
            print("ERROR: Identity Provider not configured")
            print("Fix: Console -> Settings -> Identity Bridge")
        elif "Connection refused" in err or "connect" in err.lower():
            print("ERROR: Cannot connect to MACAW")
            print("Fix: Ensure LocalAgent is running")
        else:
            print(f"ERROR: {e}")
        print("=" * 60)
        sys.exit(1)
