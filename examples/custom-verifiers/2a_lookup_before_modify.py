#!/usr/bin/env python3
"""
2a_lookup_before_modify.py - A Check That Remembers What a Tool Did

A reservations service has two tools. lookup records the reservation it
returned as a signed attestation. modify is guarded by modifiable_reservation,
a verifier written for this example: it refuses unless this caller looked up
that reservation and the reservation is not basic economy.

Demonstrates:
- A tool recording a value as an attestation: logger.attest(name, value=...).
  The tool's enforcement point signs it, not the tool.
- A verifier reading that value on a later call and comparing it with the
  call's parameters
- One record per reservation: the reservation id is part of the name
- Attestations are kept per caller: a second caller cannot use the first
  caller's lookup

Prerequisites:
    - MACAW client 0.9.21 or later (npx @macaw-ai/client install), with
      MACAW_HOME set
    - The workspace set up once, in the console:
        1. Policies > Functions > New Function: kind Verifier, name
           modifiable_reservation. Paste functions/modifiable_reservation.py
           as the source and functions/modifiable_reservation.samples.json as
           the samples; Run, then Save
        2. Policies > Add Policy: paste policies/app_reservation-demo.json, Save
      The policy is refused until the workspace has the verifier it names.

Run:
    python 2a_lookup_before_modify.py
"""

from macaw_client import MACAWClient


RESERVATIONS = {
    "E123": {"route": "SFO-CDG", "cabin": "economy"},
    "B456": {"route": "SFO-JFK", "cabin": "basic_economy"},
}

SETUP = """
  This workspace is not set up for the example. Once, in the console:
    1. Policies > Functions > New Function: kind Verifier, name
       modifiable_reservation. Paste functions/modifiable_reservation.py as
       the source and functions/modifiable_reservation.samples.json as the
       samples; Run, then Save
    2. Policies > Add Policy: paste policies/app_reservation-demo.json, Save
"""


def lookup(params, logger):
    """Return a reservation, and record which one this caller was shown."""
    rid = params.get("reservation_id")
    record = RESERVATIONS.get(rid)
    if record is None:
        return {"error": f"no reservation {rid}"}
    # The value comes from the service's own data, not from the request.
    logger.attest(f"reservation_checked/{rid}",
                  value={"reservation_id": rid, "cabin": record["cabin"]})
    return {"reservation_id": rid, **record}


def modify(params):
    """Change a reservation. modifiable_reservation decides whether this runs."""
    return {"reservation_id": params.get("reservation_id"), "modified": True}


def call(client, service, tool, rid):
    """(allowed, what came back or why it was refused, as text)"""
    try:
        result = client.invoke_tool(f"tool:reservation-demo/{tool}", {"reservation_id": rid},
                                    target_agent=service.agent_id)
    except Exception as e:
        return False, str(e)
    if isinstance(result, dict) and "error" in result:
        return False, str(result["error"])
    return True, str(result)


def main():
    print("=" * 60)
    print("Example 2a: a verifier that reads what a tool recorded")
    print("=" * 60)

    service = None
    callers = []
    try:
        # Step 1: The service that hosts both tools
        print("\n[Step 1] Registering the service...")
        service = MACAWClient(
            app_name="reservation-demo",
            agent_type="service",
            tools={"tool:reservation-demo/lookup": {"handler": lookup,
                                                    "description": "Look up a reservation"},
                   "tool:reservation-demo/modify": {"handler": modify,
                                                    "description": "Modify a reservation"}},
        )
        if not service.register():
            print("  ERROR: Failed to register the service")
            return 1
        print(f"  Service ID: {service.agent_id}")

        # Step 2: The caller
        print("\n[Step 2] Registering the caller...")
        caller = MACAWClient(app_name="reservation-demo-client", agent_type="app")
        callers.append(caller)
        if not caller.register():
            print("  ERROR: Failed to register the caller")
            return 1
        print(f"  Agent ID: {caller.agent_id}")

        # Step 3: Modify before any lookup. The verifier finds nothing recorded.
        print("\n[Step 3] Modify E123 before looking it up...")
        allowed, detail = call(caller, service, "modify", "E123")
        if allowed or "has not looked up" not in detail:
            print(f"  {'Allowed' if allowed else 'Refused'}: {detail[:96]}")
            print("  The policy's verifier did not run")
            print(SETUP)
            return 1
        print(f"  OK: refused - {detail[:96]}")

        # Step 4: Look up two reservations. Each lookup records its own.
        print("\n[Step 4] Look up E123 and B456...")
        for rid in ("E123", "B456"):
            allowed, detail = call(caller, service, "lookup", rid)
            print(f"  {rid}: {detail}")

        # Step 5: Modify the economy reservation this caller looked up.
        print("\n[Step 5] Modify E123...")
        allowed, detail = call(caller, service, "modify", "E123")
        if not allowed:
            print(f"  Refused: {detail[:96]}")
            return 1
        print(f"  OK: allowed - {detail}")

        # Step 6: Modify the basic economy reservation. The recorded cabin decides.
        print("\n[Step 6] Modify B456...")
        allowed, detail = call(caller, service, "modify", "B456")
        if allowed:
            print(f"  Allowed through: {detail}")
            return 1
        print(f"  OK: refused - {detail[:96]}")

        # Step 7: A second caller tries to use the first caller's lookup.
        print("\n[Step 7] A second caller modifies E123...")
        other = MACAWClient(app_name="reservation-demo-other", agent_type="app")
        callers.append(other)
        if not other.register():
            print("  ERROR: Failed to register the second caller")
            return 1
        allowed, detail = call(other, service, "modify", "E123")
        if allowed:
            print("  Allowed through: this client shares tool attestations across")
            print("  callers. Upgrade the MACAW client.")
            return 1
        print(f"  OK: refused - {detail[:96]}")

        print("\n" + "=" * 60)
        print("Change the policy, not the code:")
        print('  "tools": [...]     which tools modifiable_reservation guards')
        print('  "enforce": false   report what it would refuse, then promote')
        print("=" * 60)
        return 0

    finally:
        for agent in callers + [service]:
            try:
                if agent:
                    agent.unregister()
            except Exception:
                pass


if __name__ == "__main__":
    import sys
    sys.exit(main())
