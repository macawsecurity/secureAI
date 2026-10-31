def verify(invocation, context, tools=()):
    """Refuse a call to one of `tools` unless this caller looked up the
    reservation it names, and that reservation is not basic economy.
    Other tools pass."""
    if invocation.resource_id not in tools:
        return VerificationResult(True, "not a guarded tool")
    rid = invocation.params.get("reservation_id")
    record = (context.attestations or {}).get(f"reservation_checked/{rid}")
    if not record:
        return VerificationResult(False, f"this caller has not looked up reservation {rid}")
    if record["value"]["cabin"] == "basic_economy":
        return VerificationResult(False, f"reservation {rid} is basic economy and cannot be modified")
    return VerificationResult(True, f"reservation {rid} was looked up and can be modified")
