# Custom Verifiers Examples

A policy names the checks that run on a tool's calls; the enforcement point
runs them. These examples use three functions from MACAW's library:

| Function | Kind | What it does |
|---|---|---|
| `secret_scanner` | verifier | Refuses a request whose named fields carry a credential |
| `secret_scrubber` | processor | Masks credentials in a tool's result before the tool signs it |
| `secrets` | extractor | Counts the credentials in a field; the policy decides what each count means |

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

## Change the policy, not the code

| Policy setting | Effect |
|---|---|
| `"fields": ["params.script"]` | which fields the scanner reads |
| `"enforce": false` on the scanner | report what it would refuse without refusing, then promote |
| `count > 1` | how many credentials are too many |
| `"verifiers": ["secret_scanner::{...}"]` | when a check applies |
