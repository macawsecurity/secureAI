#!/usr/bin/env python3
"""
1b_extractor_threshold_bob.py - The Manager's Review

Bob lists the pending security_review requests and approves or denies each.
Alice's request is blocking, waiting for his decision.

NOTE: This example requires interactive input and is not suitable for
automated test harnesses.

Prerequisites:
    - MACAW installed (npx @macaw-ai/client install), with MACAW_HOME set
    - Identity Provider configured (Console -> Settings -> Identity Bridge)
    - Test user: bob/Bob@123! with the manager role
    - Alice's last request waiting (1b_extractor_threshold_alice.py running)

Run:
    python 1b_extractor_threshold_bob.py
"""

import json

from macaw_client import MACAWClient, RemoteIdentityProvider


def main():
    print("=" * 60)
    print("Example 1b: the manager's review (Bob)")
    print("=" * 60)

    # Step 1: Bob signs in
    print("\n[Step 1] Authenticating as bob...")
    jwt_token, _ = RemoteIdentityProvider().login("bob", "Bob@123!")
    bob = MACAWClient(user_name="bob", iam_token=jwt_token,
                      agent_type="user", app_name="secret-demo-review",
                      intent_policy={"resources": ["attestation:*"],
                                     "constraints": {"roles": ["manager"]}})
    if not bob.register():
        print("  ERROR: Failed to register Bob's agent")
        return 1
    print(f"  Agent ID: {bob.agent_id}")

    try:
        # Step 2: The requests waiting for review
        print("\n[Step 2] Pending security reviews...")
        pending = [a for a in bob.list_attestations(status="pending")
                   if str(a.get("key", "")).startswith("security_review")]
        if not pending:
            print("  None. Start 1b_extractor_threshold_alice.py first.")
            return 0

        # Step 3: Approve or deny each
        print("  Options: [y] Approve  [d] Deny  [s] Skip")
        for att in pending:
            print(f"\n  {att.get('key')} for {att.get('for_agent')}")
            if att.get("value"):
                print(f"      Request: {json.dumps(att.get('value'))[:200]}")
            answer = input("  Approve? [y/d/s]: ").strip().lower()
            if answer == "y":
                ok = bob.approve_attestation(att, reason="Reviewed: one credential, rotation planned")
                print("  APPROVED" if ok else "  Failed to approve")
            elif answer == "d":
                ok = bob.deny_attestation(att, reason="Remove the credential from the notes")
                print("  DENIED" if ok else "  Failed to deny")
            else:
                print("  Skipped")
        return 0

    finally:
        bob.unregister()


if __name__ == "__main__":
    import sys
    sys.exit(main())
