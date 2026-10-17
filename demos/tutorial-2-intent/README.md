# Tutorial 2: Intent-Based Access Control

This tutorial demonstrates intent-based access control and human-in-the-loop approval for the fictional
XYZ Fincorp, whose team works on a Databricks lakehouse through a coding agent. The same SQL tool that
reads a table can also change someone's bonus. Anyone can slip in `bonus = bonus + 20000`, and the query
never says what the final bonus will be. MACAW looks at what each query is trying to do: it runs the
query, blocks it, or holds it for an admin to approve. Controls are specified through
MAPL policies enforced by the MACAW runtime invisibly. We use Databricks as the lakehouse and Claude
Code as the coding agent. All these components are replaceable modularly.

## Why This Matters

| Problem | How MACAW handles it |
|---------|----------------------|
| A table grant allows a change or it does not. Anyone allowed to update `bonus` can set it to any amount. | MACAW's verifier parses the SQL and stamps the bonus value; the policy decides on that value. |
| A large bonus change needs a person's sign-off, not a plain allow or deny. | A bonus above 10,000 waits for an admin to approve it in the Console. |
| Anyone can slip in `bonus = bonus + 20000`; the final amount is never in the query. | MACAW cannot read the final number, so it marks the change unclear and holds it for an admin. |
| Some actions should never come from an agent. | DELETE, DROP and any query naming `hr_salaries` are blocked before they reach Databricks. |

## Overview

| Request | Example | Control |
|---------|---------|---------|
| Read | `SELECT` on `employees` | allowed |
| Bonus up to 10,000 | `SET bonus = 8000` | allowed |
| Bonus above 10,000 | `SET bonus = 15000` | admin approval (`comp_change_approved`) |
| Bonus with an unclear value | `SET bonus = bonus + 20000` | admin approval (`unclear_value`) |
| Delete or drop | `DELETE FROM employees ...` | blocked |
| Restricted table | any query naming `hr_salaries` | blocked |

## Directory Structure

```
tutorial-2-intent/
├── script.py                    # SecureMCPProxy over the Databricks SQL MCP, with the verifier
├── Policies/
│   └── app_databricks.json      # app:databricks-remote-proxy
├── utility/
│   ├── databricks_verifier.py   # DatabricksSQLVerifier
│   └── setup.sql                # demo tables and rows, run in Databricks
└── README.md
```

## Quick Start

### 1. Prerequisites

- MACAW console account
- The macaw client folder downloaded from the Console (`macaw-client-<version>-<platform>-py<version>`)
- A Databricks workspace with a SQL warehouse
- Claude Code

### 2. Install Dependencies

Create a virtual environment with the Python version in your client folder's name (`py3.12` →
Python 3.12), then install the client and the adapters into it:

```bash
export MACAW_HOME="<path to macaw-client-*>"
python3.12 -m venv .venv
source .venv/bin/activate
pip install "$MACAW_HOME"/macaw_client-*.whl "$MACAW_HOME/secureAI[all]"
pip install sqlglot==30.20.0
```

### 3. Platform Setup

Open the SQL editor in your Databricks workspace, paste `utility/setup.sql` and run it. It creates the
`workspace.xyz_fincorp` schema with two tables:

| Table | Used for |
|-------|----------|
| `employees` | the bonus changes in this tutorial |
| `hr_salaries` | the restricted table: every query naming it is blocked |

Run it again any time to reset the data.

### 4. Get the Databricks Token and MCP URL

Create a personal access token in Databricks: Settings → Developer → Access tokens. The managed SQL MCP
server is at `/api/2.0/mcp/sql` on your workspace host. Keep these two values; step 6 uses them.

```bash
export DATABRICKS_MCP_URL="https://<workspace-host>/api/2.0/mcp/sql"
export DATABRICKS_TOKEN="<your token>"
```

### 5. Load Policies

Import the policy from `Policies/` into your MACAW workspace via the Console: Policies → Add Policy →
Code Editor → paste JSON → Validate → Save.

| # | File | Policy id |
|---|---|---|
| 1 | `Policies/app_databricks.json` | `app:databricks-remote-proxy` |

#### What the policy guards

| Rule | Guardrail |
|------|-----------|
| `denied_parameters` on `execute_sql` | blocks DROP, DELETE and `hr_salaries` |
| `denied_parameters` on `execute_sql_read_only` | blocks `hr_salaries` |
| `comp_change_approved` | a bonus above 10,000 waits for an admin |
| `unclear_value` | a bonus update whose value cannot be read waits for an admin |

Both attestations are `one_time` with a `timeout` of 300: one approval clears one call, and the call
waits up to 5 minutes for it. Both need `role:admin`; in this tutorial that is you, the tenant admin.

### 6. Register the Proxy

`script.py` fronts the Databricks SQL MCP with a `SecureMCPProxy` and adds the verifier. Register it in
Claude Code as a stdio MCP server:

```bash
claude mcp add databricks-remote-proxy --scope user \
  -- bash -lc 'source <path to .venv from step 2>/bin/activate && \
     export MACAW_HOME="<path to macaw-client-*>" && \
     export DATABRICKS_MCP_URL="https://<workspace-host>/api/2.0/mcp/sql" && \
     export DATABRICKS_TOKEN="<your token>" && \
     cd <path to tutorial-2-intent> && \
     python script.py'
```

Remove with: `claude mcp remove databricks-remote-proxy`

Start a new Claude Code session so the server loads.

Then ask Claude Code to run each query in [Expected Output](#expected-output). When a call waits for
approval, approve or deny it from the Console. Once approved, the query runs.

## Custom Verifier

Custom verifiers run inside the verification pipeline before the policy decision and stamp what they
find as parameters, so MAPL can gate on them.

`utility/databricks_verifier.py`: DatabricksSQLVerifier

```python
proxy.macaw_client.agent.verification_pipeline.add_verifier(DatabricksSQLVerifier(), priority=20)
```

Its scope is `*databricks*execute_sql`, so it runs on the write tool only. The read-only tool has no
writes to read.

It parses the `query` with sqlglot, pulls out the `column = value` writes in an UPDATE, MERGE or
INSERT, and stamps two parameters per column:

| Parameter | Values | When it is set |
|-----------|--------|----------------|
| `<col>_resolution` | resolved / unresolved | set for every column it finds. Resolved means the value is a plain whole number |
| `<col>` | the number | set only when resolved, removed otherwise |

```
UPDATE t SET bonus = 15000          ->  bonus_resolution="resolved",   bonus=15000
UPDATE t SET bonus = bonus + 20000  ->  bonus_resolution="unresolved", bonus removed
```

| What it does | Why |
|--------------|-----|
| Reads the SQL structure, not the words in it | it catches the UPDATE inside a MERGE, which a top-level check misses |
| Only a plain whole number counts as known | an expression, subquery or variable could be anything |
| Removes the value when it cannot read it | nothing stale or forgeable is left for the policy to trust |
| Names no columns itself | the policy picks which columns matter, so a new one is a policy edit, not a code change |

## What the Tutorial Shows

1. **Intent**: MACAW can read what a query writes, and the policy decides on the value
2. **Human in the loop**: a large or unreadable bonus waits for an admin
3. **Hard limits**: DELETE, DROP and `hr_salaries` are blocked outright

### Expected Output

| # | Query | Result | Why |
|---|-------|--------|-----|
| 1 | `SELECT * FROM workspace.xyz_fincorp.employees` | 🟢 ALLOWED | reads are not gated |
| 2 | `SELECT * FROM workspace.xyz_fincorp.hr_salaries` | 🔴 BLOCKED | `*hr_salaries*` is in `denied_parameters` |
| 3 | `DELETE FROM workspace.xyz_fincorp.employees WHERE id = 4` | 🔴 BLOCKED | `*DELETE *` is in `denied_parameters` |
| 4 | `UPDATE workspace.xyz_fincorp.employees SET bonus = 8000 WHERE id = 1` | 🟢 ALLOWED | the bonus reads as 8000, under 10,000 |
| 5 | `UPDATE workspace.xyz_fincorp.employees SET bonus = 15000 WHERE id = 1` | 🟡 ATTESTATION | above 10,000, so `comp_change_approved` waits for an admin |
| 6 | `UPDATE workspace.xyz_fincorp.employees SET bonus = bonus + 20000 WHERE id = 1` | 🟡 ATTESTATION | the final amount cannot be read, so `unclear_value` waits for an admin |
| 7 | `MERGE INTO workspace.xyz_fincorp.employees t USING (SELECT 1 AS id) s ON t.id = s.id WHEN MATCHED THEN UPDATE SET bonus = 50000` | 🟡 ATTESTATION | the UPDATE inside the MERGE is still read, so `comp_change_approved` waits for an admin |
