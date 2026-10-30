#!/usr/bin/env python3
"""
1a_scanner_and_scrubber.py - A Policy Names the Checks

A service registers a tool that legitimately holds a credential and echoes it
back. A caller invokes it twice. The workspace policy app:secret-demo names a
verifier for the request and a processor for the result; nothing in either
script names them.

Demonstrates:
- secret_scanner, a verifier, refusing a request that carries a credential,
  before the tool runs
- secret_scrubber, a processor, masking a credential in the result before the
  tool signs it, so the signature covers what the caller receives

Inbound the scanner reports and does not rewrite: the caller signed those
parameters. Outbound the scrubber masks: the tool signs after it.

Prerequisites:
    - MACAW installed (npx @macaw-ai/client install), with MACAW_HOME set
    - The workspace set up once, in the console:
        1. Policies > Functions: under Library, Add secret_scanner,
           secret_scrubber and secrets, and Save each
        2. Policies > Add Policy: paste policies/app_secret-demo.json, Save
      The policy is refused until the workspace has the functions it names.

Run:
    python 1a_scanner_and_scrubber.py
"""

from macaw_client import MACAWClient


GITHUB_TOKEN = "ghp_" + "a" * 36
AWS_KEY = "AKIAIOSFODNN7EXAMPLE"

SETUP = """
  This workspace is not set up for the example. Once, in the console:
    1. Policies > Functions: under Library, Add secret_scanner,
       secret_scrubber and secrets, and Save each
    2. Policies > Add Policy: paste policies/app_secret-demo.json, Save
"""


def deploy(params):
    """A tool that holds a credential and echoes it back in its log."""
    return {"log": f"deployed with {GITHUB_TOKEN} ok",
            "script": params.get("script", ""),
            "exit_code": 0}


def main():
    print("=" * 60)
    print("Example 1a: secret_scanner and secret_scrubber")
    print("=" * 60)

    service = None
    caller = None
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

        # Step 2: The caller. The checks apply to the tool, whoever calls it.
        print("\n[Step 2] Registering the caller...")
        caller = MACAWClient(app_name="secret-demo-client", agent_type="app")
        if not caller.register():
            print("  ERROR: Failed to register the caller")
            return 1
        print(f"  Agent ID: {caller.agent_id}")

        # Step 3: A clean request. The processor masks what the tool returns.
        print("\n[Step 3] A clean request...")
        result = caller.invoke_tool("tool:secret-demo/run",
                                    {"script": "deploy --env staging"},
                                    target_agent=service.agent_id)
        log = (result or {}).get("log", "")
        print(f"  Returned: {log}")
        if "[REDACTED]" in log:
            print("  OK: secret_scrubber masked the token before the result was signed")
        else:
            print("  The token was NOT masked: the policy's processor did not run")
            print(SETUP)
            return 1

        # Step 4: A request carrying a credential. The verifier refuses it.
        print("\n[Step 4] A request carrying a credential...")
        try:
            result = caller.invoke_tool("tool:secret-demo/run",
                                        {"script": f"export KEY={AWS_KEY}"},
                                        target_agent=service.agent_id)
            print(f"  Allowed through: the policy's verifier did not run. Returned: {result}")
            print(SETUP)
            return 1
        except Exception as e:
            if "Credentials present" not in str(e):
                raise
            print("  OK: secret_scanner refused it before the tool ran")
            print(f"      {str(e)[:96]}")

        print("\n" + "=" * 60)
        print("Change the policy, not the code:")
        print('  "fields": [...]     what the scanner reads')
        print('  "enforce": false    report what it would refuse, then promote')
        print("=" * 60)
        return 0

    finally:
        for agent in (caller, service):
            try:
                if agent:
                    agent.unregister()
            except Exception:
                pass


if __name__ == "__main__":
    import sys
    sys.exit(main())
