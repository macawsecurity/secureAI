#!/usr/bin/env python3
"""
1a_trade_alice.py - External Attestation Trade Request

Alice wants to execute a high-value trade ($15,000).
Policy requires manager approval via external attestation for amounts > $10,000.

This demonstrates:
- Conditional attestations: only required when amount > 10000
- Blocking flow: request waits for approval
- Role-based approval: only users with role:manager can approve

NOTE: This example requires interactive approval and is not suitable
for automated test harnesses.

Prerequisites:
    - MACAW SDK installed (pip install macaw-client macaw-adapters)
    - Identity Provider configured (Console -> Settings -> Identity Bridge)
    - Test users: alice/Alice123!, bob/Bob@123! (bob needs manager role)

Run:
    # Terminal 1: Run Alice's trade request (will block waiting)
    python 1a_trade_alice.py

    # Terminal 2: Run Bob's approval
    python 1a_trade_bob.py
"""

import json

from macaw_client import MACAWClient, RemoteIdentityProvider


# Trade configuration
TRADE_SYMBOL = "AAPL"
TRADE_AMOUNT = 15000  # High-value trade requiring approval


def execute_trade_handler(params):
    """Execute trade - the actual tool implementation."""
    print(f"\n  [TOOL] execute_trade invoked!")
    print(f"  [TOOL] Received parameters:")
    print(f"         - symbol: {params.get('symbol')}")
    print(f"         - amount: ${params.get('amount'):,}")
    print(f"         - action: {params.get('action')}")

    # Simulate trade execution
    result = {
        "status": "executed",
        "symbol": params.get("symbol"),
        "amount": params.get("amount"),
        "action": params.get("action"),
        "trade_id": "TRD-12345",
        "message": f"Successfully {params.get('action')} ${params.get('amount'):,} of {params.get('symbol')}"
    }
    print(f"  [TOOL] Returning: {result}")
    return result


def main():
    print("=" * 60)
    print("Example 1a: External Attestation - Trade Request (Alice)")
    print("=" * 60)

    # Step 1: Create Trading Service (provides execute_trade tool)
    print("\n[Step 1] Creating Trading Service...")

    try:
        trading_service = MACAWClient(
            app_name="trading",
            agent_type="service",
            tools={
                "tool:trading/execute_trade": {
                    "handler": execute_trade_handler,
                    "description": "Execute a stock trade"
                }
            }
        )

        if not trading_service.register():
            print("  ERROR: Failed to register Trading Service")
            print("\n  Make sure LocalAgent is running:")
            print("    python3 -m macaw_agent.main")
            return 1

        print(f"  Service ID: {trading_service.agent_id}")
        print(f"  Provides: tool:trading/execute_trade")

    except Exception as e:
        print(f"  ERROR: Failed to create Trading Service: {e}")
        return 1

    # Step 2: Authenticate as Alice
    print("\n[Step 2] Authenticating as alice...")
    try:
        jwt_token, _ = RemoteIdentityProvider().login("alice", "Alice123!")
        print("  Got JWT token")
    except Exception as e:
        print(f"  ERROR: Failed to authenticate: {e}")
        print("\n  Make sure your identity provider is running and alice user exists")
        trading_service.unregister()
        return 1

    # Step 3: Create Alice's user agent with attestation policy
    print("\n[Step 3] Creating Alice's user agent...")
    try:
        # MAPL v3 format for attestations:
        # - "attestations" array: defines WHEN attestation is required
        # - "constraints.attestations": defines HOW attestation works
        alice = MACAWClient(
            user_name="alice",
            iam_token=jwt_token,
            agent_type="user",
            app_name="trading-app",
            intent_policy={
                "resources": ["tool:trading/execute_trade"],
                # Attestation required when amount > 10000
                "attestations": [
                    "trade-approved::{params.amount > 10000}"
                ],
                # Attestation metadata
                "constraints": {
                    "attestations": {
                        "trade-approved": {
                            "approval_criteria": "role:manager",
                            "timeout": 300,       # 5 minutes to approve
                            "time_to_live": 3600, # Valid for 1 hour after approval
                            "one_time": True      # Consumed after single use
                        }
                    }
                }
            }
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

    # Step 4: Execute trade (will block waiting for approval)
    print("\n[Step 4] Executing trade...")
    print(f"  Symbol: {TRADE_SYMBOL}")
    print(f"  Amount: ${TRADE_AMOUNT:,}")
    print(f"\n  Policy check: amount ({TRADE_AMOUNT}) > 10000 -> attestation REQUIRED")
    print(f"  Attestation: 'trade-approved' requires role:manager")
    print(f"\n  Creating PENDING attestation and BLOCKING...")
    print(f"  Bob has 5 minutes (timeout=300s) to approve.")
    print(f"\n  >>> Run 1a_trade_bob.py in another terminal <<<")
    print("-" * 60)

    try:
        # This will block internally while waiting for attestation
        result = alice.invoke_tool(
            tool_name="tool:trading/execute_trade",
            target_agent=trading_service.agent_id,
            parameters={
                "symbol": TRADE_SYMBOL,
                "amount": TRADE_AMOUNT,
                "action": "buy"
            }
        )

        print("\n" + "=" * 60)
        print("TRADE EXECUTED SUCCESSFULLY!")
        print("=" * 60)
        print(f"Result: {json.dumps(result, indent=2)}")

    except Exception as e:
        error_msg = str(e)
        if "attestation" in error_msg.lower() or "denied" in error_msg.lower():
            print("\n" + "=" * 60)
            print("TRADE BLOCKED - ATTESTATION REQUIRED OR DENIED")
            print("=" * 60)
            print(f"\nError: {error_msg}")
            print(f"\nTo approve, Bob should run:")
            print(f"  python 1a_trade_bob.py")
        else:
            print(f"\n  ERROR: {e}")

    finally:
        # Cleanup
        print("\n[Cleanup] Unregistering agents...")
        try:
            alice.unregister()
            trading_service.unregister()
        except:
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
            print("Fix: Console -> Settings -> Identity Bridge")
        elif "Connection refused" in err or "connect" in err.lower():
            print("ERROR: Cannot connect to MACAW")
            print("Fix: Ensure LocalAgent is running")
        else:
            print(f"ERROR: {e}")
        print("=" * 60)
        sys.exit(1)
