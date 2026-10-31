# Custom Verifiers Examples

A policy names the checks that run on a tool's calls; the enforcement point
runs them. Examples 1a and 1b use three functions from MACAW's library;
example 2a uses a verifier written for it, in `functions/`:

| Function | Kind | What it does |
|---|---|---|
| `secret_scanner` | verifier | Refuses a request whose named fields carry a credential |
| `secret_scrubber` | processor | Masks credentials in a tool's result before the tool signs it |
| `secrets` | extractor | Counts the credentials in a field; the policy decides what each count means |
| `modifiable_reservation` | verifier | Refuses a modify unless the same caller looked up that reservation and it is not basic economy |

A verifier decides and a processor transforms. An extractor does neither: it
reports a fact, and the policy sets the threshold.

## Setup (once per workspace)

1. **Add the functions.** In the console, open Policies > Functions. Under
   Library, click Add next to `secret_scanner`, `secret_scrubber` and
   `secrets`, and Save each.
2. **Add the policy.** Open Policies > Add Policy, paste
   `policies/app_secret-demo.json` and Save. The console refuses a policy that
   names a function the workspace does not have, so add the functions first.

The policy covers `tool:secret-demo/**`. Whoever calls the tool, these checks
apply to it.

For example 2a:

3. **Add the verifier.** Open Policies > Functions > New Function. Choose kind
   Verifier and name it `modifiable_reservation`. Paste
   `functions/modifiable_reservation.py` as the source and
   `functions/modifiable_reservation.samples.json` as the samples. Run, then
   Save.
4. **Add the policy.** Open Policies > Add Policy, paste
   `policies/app_reservation-demo.json` and Save.

## Examples

### Example 1a: Scanner and Scrubber

| File | What It Does |
|------|--------------|
| `1a_scanner_and_scrubber.py` | A service registers a tool that echoes a GitHub token; a caller invokes it twice |

- **A clean request:** the tool's result comes back as `deployed with [REDACTED] ok`.
  The scrubber masked the token before the tool signed the result, so the
  signature covers what the caller received.
- **A request carrying an AWS key in `script`:** refused before the tool runs.
  The scanner reports the credential and does not rewrite the request: the
  caller signed those parameters.

```bash
python 1a_scanner_and_scrubber.py
```

### Example 1b: Extractor Threshold

| File | Role | What It Does |
|------|------|--------------|
| `1b_extractor_threshold_alice.py` | Requester | Sends notes with 0, 2, then 1 credential; the last call waits |
| `1b_extractor_threshold_bob.py` | Approver | Lists pending security reviews, approves or denies |

| Credentials in `notes` | Outcome | Policy line |
|---|---|---|
| 0 | allowed | |
| 1 | a manager approves first | `security_review::{ derived.secrets.count == 1 }` |
| 2 or more | refused | `denied_parameters: {derived.secrets.count > 1}` |

Needs an identity provider (Console > Settings > Identity Bridge) with the test
users `alice/Alice123!` and `bob/Bob@123!`; bob needs the manager role.

```bash
# Terminal 1: Alice's requests (the last one waits up to 300s)
python 1b_extractor_threshold_alice.py

# Terminal 2: Bob approves
python 1b_extractor_threshold_bob.py
```

### Example 2a: A Check That Remembers What a Tool Did

| File | What It Does |
|------|--------------|
| `2a_lookup_before_modify.py` | A service with `lookup` and `modify` tools; a caller looks up two reservations and modifies them; a second caller tries to use the first caller's lookup |

`lookup` records the reservation it returned, from the service's own data:

```python
logger.attest(f"reservation_checked/{rid}", value={"reservation_id": rid, "cabin": cabin})
```

The tool's enforcement point signs the attestation and keeps it in the
caller's session: one session per calling principal. `modifiable_reservation`
reads it on a later `modify` and compares it with the call:

| Step | Outcome | Why |
|---|---|---|
| modify E123, nothing looked up | refused | no `reservation_checked/E123` in this caller's session |
| look up E123 and B456 | allowed | each lookup records its own reservation |
| modify E123 | allowed | looked up, economy |
| modify B456 | refused | looked up, basic economy |
| a second caller modifies E123 | refused | its session holds nothing |

The reservation id is part of the name, so each reservation keeps its own
record. Under one name, the second lookup would replace the first.

The verifier reads the attestation and spends nothing. To make it single use,
attest with `one_time=True` and require it by name in the policy's
`attestations`; see the MAPL guide, Explicit Attestation.

Attestations are held in the service's memory: a restart clears them, and
another service cannot see them. Needs client 0.9.21 or later; earlier clients
keep one set for every caller, and step 7 says so.

```bash
python 2a_lookup_before_modify.py
```

## Change the policy, not the code

| Policy setting | Effect |
|---|---|
| `"fields": ["params.script"]` | which fields the scanner reads |
| `"enforce": false` on the scanner | report what it would refuse without refusing, then promote |
| `count > 1` | how many credentials are too many |
| `"verifiers": ["secret_scanner::{...}"]` | when a check applies |
| `"tools": [...]` on `modifiable_reservation` | which tools it guards |
