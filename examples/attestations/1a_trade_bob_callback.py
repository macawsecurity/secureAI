#!/usr/bin/env python3
"""
1a_trade_bob_callback.py - Manager Approval, signed in through the browser

1a_trade_bob.py with one change: Bob signs in through the tenant's identity
provider in a browser - RemoteIdentityProvider().login_browser() - instead of
sending a username and password. Everything after sign-in is identical.

The provider's own page decides how Bob authenticates (password, MFA, passkey).
The control plane trades the result for a token and validates it through the
identity bridge, as it does for login(). This script never talks to the
provider.

Prerequisites:
    - Everything 1a_trade_bob.py needs
    - The tenant's provider client allows this redirect URI:
          <control plane>/auth/iam/callback
      e.g. http://localhost:9312/auth/iam/callback for a local control plane

    In Keycloak (admin console, http://localhost:8080/admin):
      1. Realm: the tenant's realm (e.g. fintech)
      2. Clients -> the tenant's client (e.g. financial-analyzer) -> Settings
      3. Access settings -> Valid redirect URIs -> add the URI above
      4. Capability config -> Standard flow: checked
      5. Save
    Other providers (Entra, Okta, Auth0, Google): add the same URI as a
    redirect URI on the app registration the tenant is configured with.

Run:
    # Terminal 1
    python 1a_trade_alice.py

    # Terminal 2 - a browser opens; sign in as bob
    python 1a_trade_bob_callback.py
"""

import json

from macaw_client import MACAWClient, RemoteIdentityProvider


def main():
    print("=" * 60)
    print("Example 1a: External Attestation - Manager Approval (Bob, browser sign-in)")
    print("=" * 60)

    # Step 1: Authenticate as Bob
    print("\n[Step 1] Signing in as bob in the browser...")
    try:
        jwt_token, principal = RemoteIdentityProvider().login_browser()
        print(f"  Signed in as {principal.get('user_id')}")
    except KeyboardInterrupt:
        print("\n  Sign-in cancelled.")
        return 1
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
