#!/usr/bin/env python3
"""
1b_grant_admin.py - Reusable Capability Grant (Admin Approval)

Admin approves capability grants for researchers.
Since one_time=False, this approval is REUSABLE.

This demonstrates:
- Identifying reusable vs one-time attestations
- Granting capabilities that persist
- Future invocations reuse this approval (no blocking)

NOTE: This example requires interactive input and is not suitable
for automated test harnesses.

Prerequisites:
    - MACAW SDK installed (pip install macaw-client macaw-adapters)
    - Identity Provider configured (Console -> Settings -> Identity Bridge)
    - Test users: alice/Alice123!, bob/Bob@123! (bob needs admin role)
    - Researcher script already waiting (1b_grant_researcher.py running)

Run:
    # Terminal 1: Run researcher request first
    python 1b_grant_researcher.py

    # Terminal 2: Run admin approval
    python 1b_grant_admin.py
"""

import json

from macaw_client import MACAWClient, RemoteIdentityProvider


def main():
    print("=" * 60)
    print("Example 1b: Reusable Capability Grant - Admin")
    print("=" * 60)

    # Step 1: Authenticate as admin (using bob with admin role)
    print("\n[Step 1] Authenticating as admin...")
    try:
        jwt_token, _ = RemoteIdentityProvider().login("bob", "Bob@123!")
        print("  Got JWT token")
    except Exception as e:
        print(f"  ERROR: Failed to authenticate: {e}")
        return 1

    # Step 2: Create admin agent
    print("\n[Step 2] Creating admin agent...")
    try:
        admin = MACAWClient(
            user_name="admin",
            iam_token=jwt_token,
            agent_type="user",
            app_name="admin-console",
            intent_policy={
                "resources": ["attestation:*"],
                "constraints": {
                    "roles": ["admin"]
                }
            }
        )

        if not admin.register():
            print("  ERROR: Failed to register admin agent")
            return 1

        print(f"  Agent ID: {admin.agent_id}")

    except Exception as e:
        print(f"  ERROR: {e}")
        return 1

    # Step 3: List pending attestations
    print("\n[Step 3] Listing pending attestations...")
    try:
        attestations = admin.list_attestations(status="pending")
    except Exception as e:
        print(f"  ERROR: {e}")
        admin.unregister()
        return 1

    if not attestations:
        print("  No pending attestations found.")
        print("\n  Make sure the researcher script is running and waiting.")
        admin.unregister()
        return 0

    print(f"\n  Found {len(attestations)} pending attestation(s):\n")

    for i, att in enumerate(attestations, 1):
        one_time = att.get('one_time', True)
        print(f"  [{i}] Key: {att.get('key')}")
        print(f"      For Agent: {att.get('for_agent')}")
        print(f"      Approval Criteria: {att.get('approval_criteria')}")
        print(f"      One-Time: {one_time}")
        if not one_time:
            print(f"      *** REUSABLE CAPABILITY - approval persists! ***")
        print()

    # Step 4: Approve attestation(s)
    print("[Step 4] Process attestations...")
    print("  Options: [y] Approve  [d] Deny  [s] Skip")

    for i, att in enumerate(attestations, 1):
        key = att.get('key')
        for_agent = att.get('for_agent')
        one_time = att.get('one_time', True)

        prompt = f"\n  '{key}' for {for_agent}"
        if not one_time:
            prompt += " (REUSABLE)"
        prompt += "? [y/d/s]: "

        response = input(prompt).strip().lower()

        if response == 'y':
            print(f"  Approving...")
            try:
                if admin.approve_attestation(att, reason="Admin granted capability"):
                    print(f"  APPROVED")
                    if not one_time:
                        print(f"  *** This approval will be REUSED for future invocations ***")
                else:
                    print(f"  Failed to approve")
            except Exception as e:
                print(f"  ERROR: {e}")

        elif response == 'd':
            print(f"  Denying...")
            try:
                if admin.deny_attestation(att, reason="Admin denied capability"):
                    print(f"  DENIED")
                else:
                    print(f"  Failed to deny")
            except Exception as e:
                print(f"  ERROR: {e}")

        else:
            print(f"  Skipped")

    # Cleanup
    admin.unregister()

    print("\n" + "=" * 60)
    print("Done. Researcher should now proceed.")
    print("Future invocations will reuse this approval (no blocking).")
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
