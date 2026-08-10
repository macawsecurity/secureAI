#!/usr/bin/env python3
"""
1a_login_alice.py - Phishing-Resistance (login-strength gating)

The simplest phishing-resistance example: a tool that only runs if the
human behind the agent logged in with a phishing-resistant method
(passkey / hardware key / WebAuthn).

There is no human in the loop and no waiting. When the user authenticates,
their token carries an `amr` (authentication methods) claim describing how
they logged in — `fido`/`hwk` for a passkey, `pwd` for a password. The
control plane reads it at LOGIN and, if the login was phishing-resistant,
mints an internal `phishing_resistant` grant for the agent. The Policy
Enforcement Point then allows or denies with no prompt.

Run it TWICE, changing only how you log in (via get_token.py):
    PASSKEY   -> amr:["fido"]        -> phishing-resistant  -> ALLOWED
    PASSWORD  -> amr:["pwd","mfa"]   -> not                 -> DENIED

That single variable — the login method — is the whole lesson.

NOTE: no approver is involved here. 1b_trade_alice.py shows the same gate
used as a precondition in front of a human approval step.

Prerequisites:
    - MACAW control plane running (LocalAgent)
    - Entra (Azure AD) connector configured in Console -> Settings -> Identity Bridge
    - An Entra user with a passkey enrolled (for the ALLOW run)
    - A token minted by get_token.py (sets ~/.macaw_demo_token / ALICE_TOKEN)

Run:
    python get_token.py                       # sign in: passkey (ALLOW) or password (DENY)
    export ALICE_TOKEN=$(cat ~/.macaw_demo_token)
    python 1a_login_alice.py
"""

import json
import os

from macaw_client import MACAWClient


# Any amount — there is no threshold here; phishing_resistant is unconditional.
TRADE_SYMBOL = "AAPL"
TRADE_AMOUNT = 500


def execute_trade_handler(params):
    """Execute trade - the actual tool implementation."""
    print(f"\n  [TOOL] execute_trade invoked!")
    print(f"         - symbol: {params.get('symbol')}")
    print(f"         - amount: ${params.get('amount'):,}")
    print(f"         - action: {params.get('action')}")
    return {
        "status": "executed",
        "symbol": params.get("symbol"),
        "amount": params.get("amount"),
        "action": params.get("action"),
        "trade_id": "TRD-00001",
        "message": f"Successfully {params.get('action')} ${params.get('amount'):,} of {params.get('symbol')}",
    }


def main():
    print("=" * 60)
    print("Example 1a: Phishing-Resistance - Login Gating (Alice)")
    print("=" * 60)

    # Step 1: Create the Trading Service (provides execute_trade)
    print("\n[Step 1] Creating Trading Service...")
    try:
        trading_service = MACAWClient(
            app_name="trading",
            agent_type="service",
            tools={
                "tool:trading/execute_trade": {
                    "handler": execute_trade_handler,
                    "description": "Execute a stock trade",
                }
            },
        )
        if not trading_service.register():
            print("  ERROR: Failed to register Trading Service")
            print("  Make sure the control plane is running: python3 -m macaw_agent.main")
            return 1
        print(f"  Service ID: {trading_service.agent_id}")
    except Exception as e:
        print(f"  ERROR: Failed to create Trading Service: {e}")
        return 1

    # Step 2: Authenticate as Alice (token from get_token.py)
    print("\n[Step 2] Authenticating as alice...")
    #   passkey login  -> amr:fido    -> phishing-resistant  (ALLOW run)
    #   password login -> amr:pwd/mfa -> not                 (DENY run)
    jwt_token = os.environ.get("ALICE_TOKEN")
    if not jwt_token and os.path.exists(os.path.expanduser("~/.macaw_demo_token")):
        jwt_token = open(os.path.expanduser("~/.macaw_demo_token")).read().strip()
    if not jwt_token:
        print("  ERROR: no ALICE_TOKEN — run get_token.py first")
        trading_service.unregister()
        return 1
    print("  Got JWT token")

    # Step 3: Create Alice's user agent — gated ONLY by phishing_resistant
    print("\n[Step 3] Creating Alice's user agent...")
    try:
        alice = MACAWClient(
            user_name="alice",
            iam_token=jwt_token,
            agent_type="user",
            app_name="trading-app",
            intent_policy={
                "resources": ["tool:trading/execute_trade"],
                # The one and only gate: the human must have logged in with a
                # phishing-resistant method. Deny-if-absent — no approver, no wait.
                "attestations": ["phishing_resistant"],
            },
        )
        if not alice.register():
            print("  ERROR: Failed to register Alice's agent")
            trading_service.unregister()
            return 1
        print(f"  Agent ID: {alice.agent_id}")
    except Exception as e:
        print(f"  ERROR: Failed to create Alice's agent: {e}")
        trading_service.unregister()
        return 1

    # Step 4: Invoke the gated tool — allowed iff the login was phishing-resistant
    print("\n[Step 4] Invoking gated tool (no approver, no waiting)...")
    print("  Gate: attestation 'phishing_resistant' must be present for alice@trading-app")
    print("-" * 60)
    try:
        result = alice.invoke_tool(
            tool_name="tool:trading/execute_trade",
            target_agent=trading_service.agent_id,
            parameters={"symbol": TRADE_SYMBOL, "amount": TRADE_AMOUNT, "action": "buy"},
        )
        print("\n" + "=" * 60)
        print("ALLOWED — login was phishing-resistant (amr:fido)")
        print("=" * 60)
        print(f"Result: {json.dumps(result, indent=2)}")
    except Exception as e:
        error_msg = str(e)
        if "phishing_resistant" in error_msg or "attestation" in error_msg.lower() or "denied" in error_msg.lower():
            print("\n" + "=" * 60)
            print("DENIED — login was NOT phishing-resistant")
            print("=" * 60)
            print(f"\nReason: {error_msg}")
            print("\nRe-run get_token.py and sign in with a PASSKEY to get the ALLOW path.")
        else:
            print(f"\n  ERROR: {e}")
    finally:
        print("\n[Cleanup] Unregistering agents...")
        try:
            alice.unregister()
            trading_service.unregister()
        except Exception:
            pass

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
            print("Fix: Console -> Settings -> Identity Bridge (add the Entra connector)")
        elif "Connection refused" in err or "connect" in err.lower():
            print("ERROR: Cannot connect to MACAW")
            print("Fix: Ensure the control plane (LocalAgent) is running")
        else:
            print(f"ERROR: {e}")
        print("=" * 60)
        sys.exit(1)
