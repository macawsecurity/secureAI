#!/usr/bin/env python3
"""
1a_trade_bob.py - External Attestation Manager Approval

Bob reviews and approves/denies pending attestation requests.
Alice's trade request is BLOCKING, waiting for Bob's approval.

This demonstrates:
- list_attestations(): Find pending requests you can approve
- approve_attestation(): Grant the request
- deny_attestation(): Reject the request with reason

NOTE: This example requires interactive input and is not suitable
for automated test harnesses.

Prerequisites:
    - MACAW SDK installed (pip install macaw-client macaw-adapters)
    - Identity Provider configured (Console -> Settings -> Identity Bridge)
    - Test users: alice/Alice123!, bob/Bob@123! (bob needs manager role)
    - Alice has already requested a trade (1a_trade_alice.py running)

Run:
    # Terminal 1: Run Alice's trade request first
    python 1a_trade_alice.py

    # Terminal 2: Run Bob's approval
    python 1a_trade_bob.py
"""

import json

from macaw_client import MACAWClient, RemoteIdentityProvider


def main():
    print("=" * 60)
    print("Example 1a: External Attestation - Manager Approval (Bob)")
    print("=" * 60)

    # Step 1: Authenticate as Bob
    print("\n[Step 1] Authenticating as bob...")
    try:
        jwt_token, _ = RemoteIdentityProvider().login("bob", "Bob@123!")
        print("  Got JWT token")
    except Exception as e:
        print(f"  ERROR: Failed to authenticate: {e}")
        print("\n  Make sure your identity provider is running and bob user exists")
        return 1

    # Step 2: Create Bob's user agent
    print("\n[Step 2] Creating Bob's user agent...")
    try:
        bob = MACAWClient(
            user_name="bob",
            iam_token=jwt_token,
            agent_type="user",
            app_name="attestation-manager",
            intent_policy={
                "resources": ["attestation:*"],
                "constraints": {
                    "roles": ["manager"]
                }
            }
        )

        if not bob.register():
            print("  ERROR: Failed to register Bob's agent")
            print("\n  Make sure LocalAgent is running:")
            print("    python3 -m macaw_agent.main")
            return 1

        print(f"  Agent ID: {bob.agent_id}")

    except Exception as e:
        print(f"  ERROR: Failed to create Bob's agent: {e}")
        return 1

    # Step 3: List pending attestations
    print("\n[Step 3] Listing pending attestations...")
    try:
        attestations = bob.list_attestations(status="pending")
    except Exception as e:
        print(f"  ERROR: Failed to list attestations: {e}")
        bob.unregister()
        return 1

    if not attestations:
        print("  No pending attestations found.")
        print("\n  Make sure Alice has requested a trade first:")
        print("    python 1a_trade_alice.py")
        bob.unregister()
        return 0

    print(f"\n  Found {len(attestations)} pending attestation(s):\n")

    for i, att in enumerate(attestations, 1):
        print(f"  [{i}] Key: {att.get('key')}")
        print(f"      For Agent: {att.get('for_agent')}")
        print(f"      Approval Criteria: {att.get('approval_criteria')}")
        print(f"      One-Time: {att.get('one_time', False)}")
        if att.get('value'):
            print(f"      Value: {json.dumps(att.get('value', {}))}")
        print()

    # Step 4: Approve/Deny attestation(s)
    print("[Step 4] Process attestations...")
    print("  Options: [y] Approve  [d] Deny  [s] Skip")

    for i, att in enumerate(attestations, 1):
        key = att.get('key')
        for_agent = att.get('for_agent')

        response = input(f"\n  '{key}' for {for_agent}? [y/d/s]: ").strip().lower()

        if response == 'y':
            print(f"  Approving...")
            try:
                if bob.approve_attestation(att, reason="Manager approved"):
                    print(f"  APPROVED - Alice's request will proceed")
                else:
                    print(f"  Failed to approve")
            except Exception as e:
                print(f"  ERROR: {e}")

        elif response == 'd':
            print(f"  Denying...")
            try:
                if bob.deny_attestation(att, reason="Manager denied"):
                    print(f"  DENIED - Alice's request will be rejected")
                else:
                    print(f"  Failed to deny")
            except Exception as e:
                print(f"  ERROR: {e}")

        else:
            print(f"  Skipped")

    # Cleanup
    bob.unregister()

    print("\n" + "=" * 60)
    print("Done. Alice's request should now proceed (or fail if denied).")
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
