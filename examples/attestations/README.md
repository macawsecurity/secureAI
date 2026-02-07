# External Attestations Examples

These examples demonstrate **human-in-the-loop approval workflows** using MACAW's external attestation system.

## What Are External Attestations?

External attestations require a **third party** (manager, admin, compliance officer) to approve an operation before it can proceed. The request **blocks** while waiting for approval.

**Use cases:**
- High-value trades requiring manager sign-off
- Sensitive operations needing compliance review
- Capability grants for elevated access
- Time-boxed permissions

## Examples

### Example 1a: One-Time Trade Approval

A high-value trade ($15,000) requires manager approval. Each trade needs fresh approval.

| File | Role | What It Does |
|------|------|--------------|
| `1a_trade_alice.py` | Requester | Requests trade, blocks waiting for approval |
| `1a_trade_bob.py` | Approver | Lists pending requests, approves/denies |

**Key concepts:**
- Conditional attestation: `trade-approved::{params.amount > 10000}`
- Role-based approval: `approval_criteria: "role:manager"`
- One-time use: `one_time: True` (consumed after single use)

**Run:**
```bash
# Terminal 1: Alice requests trade (blocks)
python 1a_trade_alice.py

# Terminal 2: Bob approves (while Alice waits)
python 1a_trade_bob.py
```

### Example 1b: Reusable Capability Grant

A researcher needs admin approval for web search capability. Approve once, use many times.

| File | Role | What It Does |
|------|------|--------------|
| `1b_grant_researcher.py` | Requester | First call blocks, subsequent calls instant |
| `1b_grant_admin.py` | Approver | Grants reusable capability |

**Key concepts:**
- Reusable grant: `one_time: False`
- Time-to-live: `time_to_live: 3600` (1 hour)
- First call blocks, second+ calls immediate

**Run:**
```bash
# Terminal 1: Researcher requests (blocks on first call)
python 1b_grant_researcher.py

# Terminal 2: Admin approves (while researcher waits)
python 1b_grant_admin.py

# Watch Terminal 1: First call completes, then 2nd and 3rd are instant!
```

## Prerequisites

1. **MACAW LocalAgent running:**
   ```bash
   python3 -m macaw_agent.main
   ```

2. **Identity provider configured** (Keycloak or Auth0)
   - See `demos/tutorial-1/setup/` for setup scripts

3. **Users created in IDP:**
   - `alice` - trader/researcher
   - `bob` - manager/admin with appropriate role

## Key APIs

### Requester Side

```python
from macaw_client import MACAWClient

# Define attestation in policy
intent_policy = {
    "attestations": ["trade-approved::{params.amount > 10000}"],
    "constraints": {
        "attestations": {
            "trade-approved": {
                "approval_criteria": "role:manager",
                "timeout": 300,       # Block up to 5 minutes
                "one_time": True      # Or False for reusable
            }
        }
    }
}

# invoke_tool blocks until approved/denied/timeout
result = client.invoke_tool("tool:trading/execute", params)
```

### Approver Side

```python
from macaw_client import MACAWClient

# List pending attestations you can approve
attestations = client.list_attestations(status="pending")

# Approve or deny
client.approve_attestation(att, reason="Approved for Q4")
client.deny_attestation(att, reason="Budget exceeded")
```

## One-Time vs Reusable

| Setting | Behavior | Use Case |
|---------|----------|----------|
| `one_time: True` | Consumed after single use | High-value trades |
| `one_time: False` | Reusable until TTL expires | Capability grants |

## Learn More

- **MAPL Policy Guide**: Full attestation syntax and semantics
- **Dev Hub Tutorials**: Step-by-step walkthrough with diagrams
- **Console > Activity**: View attestation audit events
