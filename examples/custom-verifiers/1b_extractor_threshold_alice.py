#!/usr/bin/env python3
"""
1b_extractor_threshold_alice.py - Facts, Not a Verdict

The verifier in 1a can only refuse. An extractor answers a question instead:
the secrets extractor reads params.notes and reports how many credentials it
found, and the policy decides what each count means:

    0 credentials   allowed
    1 credential    security_review: a manager approves first
    2 or more       refused (denied_parameters: derived.secrets.count > 1)

The thresholds are lines in the policy, so changing them needs no code.

NOTE: The last call blocks until Bob approves it, so this example is not
suitable for automated test harnesses.

Prerequisites:
    - MACAW installed (npx @macaw-ai/client install), with MACAW_HOME set
    - The workspace set up once, in the console:
        1. Policies > Functions: under Library, Add secret_scanner,
           secret_scrubber and secrets, and Save each
        2. Policies > Add Policy: paste policies/app_secret-demo.json, Save
    - Identity Provider configured (Console -> Settings -> Identity Bridge)
    - Test users: alice/Alice123!, bob/Bob@123! (bob needs manager role)

Run:
    # Terminal 1: Alice's requests (the last one waits)
    python 1b_extractor_threshold_alice.py

    # Terminal 2: Bob approves
    python 1b_extractor_threshold_bob.py
"""

from macaw_client import MACAWClient, RemoteIdentityProvider


GITHUB_TOKEN = "ghp_" + "a" * 36
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"


def deploy(params):
    """The tool. It runs only when the policy allows the call."""
    return {"log": f"deployed: {params.get('script', '')}", "exit_code": 0}


def call(alice, service, notes):
    return alice.invoke_tool("tool:secret-demo/run",
                             # notes first: the summary the approver sees
                             # lists parameters in order
                             {"notes": notes, "script": "deploy --env staging"},
                             target_agent=service.agent_id)


def main():
    print("=" * 60)
    print("Example 1b: the secrets extractor and the policy's thresholds (Alice)")
    print("=" * 60)

    service = None
    alice = None
    try:
        # Step 1: The service that hosts tool:secret-demo/run
        print("\n[Step 1] Registering the service...")
        service = MACAWClient(
            app_name="secret-demo",
            agent_type="service",
            tools={"tool:secret-demo/run": {"handler": deploy,
                                            "description": "Run a deploy script"}},
        )
        if not service.register():
            print("  ERROR: Failed to register the service")
            return 1
        print(f"  Service ID: {service.agent_id}")

        # Step 2: Alice signs in. An approval is requested for a person.
        print("\n[Step 2] Authenticating as alice...")
        jwt_token, _ = RemoteIdentityProvider().login("alice", "Alice123!")
        alice = MACAWClient(user_name="alice", iam_token=jwt_token,
                            agent_type="user", app_name="secret-demo-client")
        if not alice.register():
            print("  ERROR: Failed to register Alice's agent")
            return 1
        print(f"  Agent ID: {alice.agent_id}")

        # Step 3: Either side of the threshold
        print("\n[Step 3] Zero credentials, then two...")
        for label, notes in [("0 credentials", "rotate the staging key next week"),
                             ("2 credentials", f"rotate {AWS_KEY} and {GITHUB_TOKEN}")]:
            try:
                call(alice, service, notes)
                print(f"  {label}: allowed")
            except Exception as e:
                print(f"  {label}: refused")
                print(f"      {str(e)[:120]}")

        # Step 4: One credential is neither allowed nor refused
        print("\n[Step 4] One credential...")
        print("  policy: security_review::{ derived.secrets.count == 1 }")
        print("  Waiting for a manager to approve (timeout 300s).")
        print("\n  >>> Run 1b_extractor_threshold_bob.py in another terminal <<<")
        print("-" * 60)
        try:
            result = call(alice, service, f"rotate {AWS_KEY}")
            print("\n  APPROVED: the call proceeded")
            print(f"      returned: {(result or {}).get('log', '')}")
        except Exception as e:
            print("\n  NOT APPROVED: the call was refused rather than executed")
            print(f"      {str(e)[:120]}")

        print("\n" + "=" * 60)
        print("The same fact refuses at two and asks a person at one.")
        print('Raise "count > 1" to "count > 2" and the second call is allowed.')
        print("=" * 60)
        return 0

    finally:
        for agent in (alice, service):
            try:
                if agent:
                    agent.unregister()
            except Exception:
                pass


if __name__ == "__main__":
    import sys
    sys.exit(main())
