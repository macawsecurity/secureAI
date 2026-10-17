# Tutorial 3: Object-Based Access Control

This tutorial demonstrates MAPL object policies, continuing Tutorial 2 at XYZ Fincorp. A policy
usually attaches to a caller: a team, a user, a service. A table is never called. A tool reads it, so
nothing loads a policy for it. An object policy attaches the rules to the table itself, and MACAW
enforces them whenever a tool touches that table, whoever the caller is. Here every Databricks table
is an object: MACAW reads which tables a query names and loads each table's policy. A table with no
policy falls back to `databricks:base`. Controls are specified through MAPL policies enforced by the
MACAW runtime invisibly. We use Databricks as the lakehouse and Claude Code as the coding agent. All
these components are replaceable modularly.

## Why This Matters

| Problem | How MACAW handles it |
|---------|----------------------|
| One SQL tool reaches every table in the workspace. | Each table gets its own policy. MACAW picks the right one per query from the tables the query names. |
| A sensitive table needs tighter limits than the rest. | Its policy narrows the schema policy and leaves the other tables untouched. |
| Text matching on SQL is easy to slip past: `Delete from` gets around `*DELETE *`. | MACAW reads the parsed query: which tables, which statement. |
| A new table has no rule yet. | It falls back to `databricks:base`: SELECT only, and an admin approves each read. |

## Overview

The app policy carries the reference `databricks:{params.table}`. MACAW's verifier stamps every table the
query names as `catalog/schema/table`, and MACAW resolves the reference per table:

- **Policy exists** → it extends the schema policy `databricks:schema/workspace/xyz_fincorp` and can only
  narrow it.
- **No policy** → falls back to `databricks:base`.

| Object | Policy | Effect |
|--------|--------|--------|
| Schema `xyz_fincorp` | `databricks:schema/workspace/xyz_fincorp` | SELECT, INSERT and UPDATE only |
| Table `employees` | `databricks:workspace/xyz_fincorp/employees` | SELECT and UPDATE only, plus the bonus rules from Tutorial 2 |
| Table `hr_salaries` | `databricks:workspace/xyz_fincorp/hr_salaries` | every query blocked |

## Directory Structure

```
tutorial-3-gating-object/
├── script.py                    # SecureMCPProxy over the Databricks SQL MCP, with MACAW's verifiers
├── Policies/
│   ├── app_databricks.json      # app:databricks-object-proxy
│   ├── base.json                # databricks:base
│   ├── schema_xyz_fincorp.json  # databricks:schema/workspace/xyz_fincorp
│   ├── employees.json           # databricks:workspace/xyz_fincorp/employees
│   └── hr_salaries.json         # databricks:workspace/xyz_fincorp/hr_salaries
├── utility/
│   ├── databricks_verifier.py   # DatabricksTableVerifier + DatabricksSQLVerifier
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
| `employees` | a table with its own policy |
| `hr_salaries` | the restricted table: every query on it is blocked |

If you ran Tutorial 2, the tables are already there. Run it again any time to reset the data.

### 4. Get the Databricks Token and MCP URL

Create a personal access token in Databricks: Settings → Developer → Access tokens. The managed SQL MCP
server is at `/api/2.0/mcp/sql` on your workspace host. Keep these two values; step 6 uses them.

```bash
export DATABRICKS_MCP_URL="https://<workspace-host>/api/2.0/mcp/sql"
export DATABRICKS_TOKEN="<your token>"
```

### 5. Load Policies

Import the policies from `Policies/` into your MACAW workspace via the Console: Policies → Add Policy →
Code Editor → paste JSON → Validate → Save. Load them in this order, because the table policies extend the
schema policy.

| # | File | Policy id |
|---|---|---|
| 1 | `Policies/app_databricks.json` | `app:databricks-object-proxy` |
| 2 | `Policies/base.json` | `databricks:base` |
| 3 | `Policies/schema_xyz_fincorp.json` | `databricks:schema/workspace/xyz_fincorp` |
| 4 | `Policies/employees.json` | `databricks:workspace/xyz_fincorp/employees` |
| 5 | `Policies/hr_salaries.json` | `databricks:workspace/xyz_fincorp/hr_salaries` |

#### Policy Hierarchy

```
app:databricks-object-proxy
    every SQL call  attests  databricks:{params.table}
                                         │
             ┌───────────────────────────┴──────────────────┐
    table policy exists                              no such policy
             │                                              │
databricks:workspace/xyz_fincorp/<table>             databricks:base
  extends databricks:schema/workspace/xyz_fincorp    SELECT only + admin_approval_required
```

A table policy can only narrow the schema policy, never widen it. A new table in `xyz_fincorp` with no
policy of its own goes to `databricks:base`, not to the schema policy.

### 6. Register the Proxy

`script.py` fronts the Databricks SQL MCP with a `SecureMCPProxy` and adds MACAW's verifiers. Register it
in Claude Code as a stdio MCP server:

```bash
claude mcp add databricks-object-proxy --scope user \
  -- bash -lc 'source <path to .venv from step 2>/bin/activate && \
     export MACAW_HOME="<path to macaw-client-*>" && \
     export DATABRICKS_MCP_URL="https://<workspace-host>/api/2.0/mcp/sql" && \
     export DATABRICKS_TOKEN="<your token>" && \
     cd <path to tutorial-3-gating-object> && \
     python script.py'
```

Remove with: `claude mcp remove databricks-object-proxy`

Start a new Claude Code session so the server loads.

Then ask Claude Code to run each query in [Expected Output](#expected-output). When a call waits for
approval, approve or deny it from the Console. Once approved, the query runs. The decision and the
reason for every call are in the Console under Logs.

## Custom Verifiers

Custom verifiers run inside the verification pipeline before the policy decision and stamp what they
find as parameters, so MAPL can gate on them.

`utility/databricks_verifier.py`: DatabricksTableVerifier and DatabricksSQLVerifier

```python
proxy.macaw_client.agent.verification_pipeline.add_verifier(DatabricksTableVerifier(), priority=10)
proxy.macaw_client.agent.verification_pipeline.add_verifier(DatabricksSQLVerifier(), priority=20)
```

MACAW's table verifier (DatabricksTableVerifier) runs on both SQL tools. MACAW's bonus verifier
(DatabricksSQLVerifier) is the one from Tutorial 2. It runs on `execute_sql` and reads the bonus value.

| Parameter | Example | Set by |
|-----------|---------|--------|
| `table` | `"workspace/xyz_fincorp/employees"` | MACAW's table verifier: the table the query names, a list when it names several |
| `stmt_type` | `select`, `update`, `insert`, `delete` | MACAW's table verifier, from the parsed statement |
| `bonus_resolution`, `bonus` | `resolved`, `15000` | MACAW's bonus verifier (Tutorial 2) |

```
SELECT * FROM workspace.xyz_fincorp.employees  ->  table="workspace/xyz_fincorp/employees", stmt_type="select"
... employees e JOIN hr_salaries h ...         ->  table=["workspace/xyz_fincorp/employees", "workspace/xyz_fincorp/hr_salaries"]
```

| What it does | Why |
|--------------|-----|
| Stamps every table in a JOIN, subquery or MERGE | each table's policy is checked, and all must pass |
| Always sets `table`, replacing any value the caller sent | the caller cannot pick which policy applies |
| Reads the statement type from the parsed SQL | `Delete from` is a delete, in any case |
| A query that names no table gets `unknown` | it goes to `databricks:base` |
| Denies SHOW, and two statements sent in one call | it cannot tell which tables they touch |

## What the Tutorial Shows

1. **Object resolution**: MACAW resolves `databricks:{params.table}` to the policy of each table a query names
2. **Inheritance**: a table policy extends its schema policy and can only narrow it
3. **Fallback**: a table with no policy resolves to `databricks:base` and waits for an admin
4. **Intent, carried over**: the bonus rules from Tutorial 2 now live in the `employees` policy

### Expected Output

| # | Query | Result | Why |
|---|-------|--------|-----|
| 1 | `SELECT * FROM workspace.xyz_fincorp.employees` | 🟢 ALLOWED | `employees` allows SELECT |
| 2 | `UPDATE workspace.xyz_fincorp.employees SET bonus = 8000 WHERE id = 1` | 🟢 ALLOWED | UPDATE allowed, bonus under 10,000 |
| 3 | `UPDATE workspace.xyz_fincorp.employees SET bonus = 15000 WHERE id = 1` | 🟡 ATTESTATION | `comp_change_approved` waits for an admin |
| 4 | `INSERT INTO workspace.xyz_fincorp.employees (id, name) VALUES (5, 'Lee Park')` | 🔴 BLOCKED | `employees` narrows the schema: no INSERT |
| 5 | `Delete from workspace.xyz_fincorp.employees WHERE id = 4` | 🔴 BLOCKED | the statement is a delete, and the schema allows none |
| 6 | `SELECT * FROM workspace.xyz_fincorp.hr_salaries` | 🔴 BLOCKED | `hr_salaries` blocks every query |
| 7 | `SELECT e.name FROM workspace.xyz_fincorp.employees e JOIN workspace.xyz_fincorp.hr_salaries h ON e.id = h.id` | 🔴 BLOCKED | both tables are checked, and `hr_salaries` blocks it |
| 8 | `SELECT 1` | 🟡 ATTESTATION | names no table, so it falls back to `databricks:base` → `admin_approval_required` |
