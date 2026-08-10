# Phishing-Resistance Examples

These examples demonstrate **login-strength gating**: a tool runs only if the
human behind the agent authenticated with a **phishing-resistant** method
(passkey / hardware key / WebAuthn).

## What Is Phishing-Resistance?

When a user authenticates, their token carries an `amr` (authentication
methods) claim describing *how* they logged in — `fido`/`hwk` for a passkey,
`pwd` for a password. At registration the control plane reads `amr` and, if the
login was phishing-resistant, mints an **internal** `phishing_resistant` grant
for that agent. A policy that lists `phishing_resistant` then allows or denies
with **no human in the loop and no waiting**.

This is the opposite of an [external attestation](../attestations/) like
`trade-approved`, which *blocks* while a manager approves:

| | `phishing_resistant` | `trade-approved` |
|---|---|---|
| decided by | the control plane, at login, from `amr` | a human approver (role:manager) |
| flow | deny-if-absent, immediate | blocks and waits |
| console | an **Active Grant** (never a pending request) | a pending HITL request |
| reusable | yes (`one_time=False`, TTL = token lifetime) | configurable |

**Use cases:** gating high-risk tools behind hardware-backed auth; requiring
step-up/passkey login before sensitive operations; layering a login-strength
check in front of a human approval.

## Getting a token

Both examples read a token from `get_token.py`, which signs you in to Entra and
saves an id_token that carries `amr`:

```bash
python get_token.py                       # a browser opens — choose how to sign in:
                                          #   PASSKEY  -> amr:["fido"]      -> ALLOW
                                          #   PASSWORD -> amr:["pwd","mfa"] -> DENY
export ALICE_TOKEN=$(cat ~/.macaw_demo_token)
```

## Examples

### Example 1a: Login gating (Alice alone)

The simplest form — one agent, one gate, **no approver**. Run it twice, changing
only how you log in.

| File | Role | What It Does |
|------|------|--------------|
| `1a_login_alice.py` | User | Invokes a `phishing_resistant`-gated tool; allowed or denied by login method |

**Key concepts:**
- The only gate: `"attestations": ["phishing_resistant"]`
- No `constraints` block, no approver, no blocking — the decision is immediate
- `PASSKEY` → allowed; `PASSWORD` → denied

**Run:**
```bash
python get_token.py            # sign in with a PASSKEY
export ALICE_TOKEN=$(cat ~/.macaw_demo_token)
python 1a_login_alice.py       # ALLOWED

# now re-run get_token.py, sign in with a PASSWORD, and repeat:
python 1a_login_alice.py       # DENIED at phishing_resistant
```

### Example 1b: Precondition to human approval (Alice + Bob)

Builds on the [alice/bob trade example](../attestations/) by **layering two
gates** on the same trade: `phishing_resistant` (internal, first) then
`trade-approved` (human, blocking, only when amount > $10,000).

| File | Role | What It Does |
|------|------|--------------|
| `1b_trade_alice.py` | Requester | Clears the phishing gate, then blocks for manager approval |
| `1b_trade_bob.py` | Approver | Lists pending requests, approves/denies the trade |

**Key concepts:**
- Two attestations in one policy: `["phishing_resistant", "trade-approved::{params.amount > 10000}"]`
- `phishing_resistant` is checked **first** — a weak login is denied before the trade ever reaches the manager gate
- On the DENY (password) run, `bob` is never involved

**Run:**
```bash
python get_token.py            # sign in with a PASSKEY
export ALICE_TOKEN=$(cat ~/.macaw_demo_token)

# Terminal 1: Alice (clears phishing gate, then blocks on approval)
python 1b_trade_alice.py

# Terminal 2: Bob approves
python 1b_trade_bob.py
```

## Prerequisites

1. **MACAW control plane running** (LocalAgent):
   ```bash
   python3 -m macaw_agent.main
   ```
2. **Entra (Azure AD) connector configured** — Console → Settings → Identity
   Bridge. `get_token.py` uses Entra's v1.0 endpoint because only v1.0 id_tokens
   carry `amr`.
3. **An Entra user with a passkey enrolled** (for the ALLOW run). Sign in with a
   password to see the DENY run.
4. **For 1b only:** an approver (`bob`) with `role:manager` — same setup as the
   [attestations](../attestations/) demo.

## How the grant works (under the hood)

- Captured at **login** (`iam_validate`) from the raw token `amr`; the grant is
  minted at **registration**, keyed by the agent id (`alice@trading-app`),
  signed by the tenant attestor, `one_time=False`, TTL = token lifetime.
- A weaker re-login (password after passkey) **revokes** the prior grant, so a
  session can't inherit a stronger login's resistance.
- It is an **internal** grant: it never appears as an approvable request in the
  console — it shows read-only under **Active Grants**.

## Learn More

- [`examples/attestations/`](../attestations/) — external (human) attestations
- **MAPL Policy Guide** — full attestation syntax and semantics
- **Console → Activity** — view the grant and its audit events
